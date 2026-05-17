// ============================================================
// File   : FB_OfflineParamEstimator.st
// 用途   : 基于历史数据估计ILC最优 (L, λ, α) 三参数
//          - 输入:FB_DataLogger 计算出的聚合指标
//          - 输出:推荐参数 + 置信度 + 诊断码
//          - 算法:工程经验启发式(非梯度下降/网格搜索,适合PLC实时性)
//
// 调用方式: bExecute 上升沿触发一次估计
//          典型工作流:
//            1. ILC 启动,运行 30 个周期采集数据
//            2. 在HMI上触发 bExecute = TRUE
//            3. 读取 rL_Recommended, rLambda_Recommended, rAlpha_Recommended
//            4. 操作员确认后写入 ILC 输入参数,重置 ILC 重新学习
//
// 启发式依据:
//   L  (学习增益) : 由 RMS 衰减率反推
//                  ρ_衰减 = 1 - exp(L·G·Δlog(RMS))
//                  目标 ρ ≈ 0.2~0.3 / 周期(快速且不振荡)
//   λ  (同步耦合) : 由 同步误差/跟踪误差 比值 给出
//                  比值高 → λ加大,比值低 → λ减小
//   α  (遗忘因子) : 由 重复性指标 决定
//                  重复性高 → α=0.99,低 → α=0.95
// ============================================================

TYPE ST_EstimatorDiag :
STRUCT
    iCode      : INT;       // 诊断码:见状态码定义
    rConfidence: REAL;      // 0~1 置信度
    sReason    : STRING(80);
END_STRUCT
END_TYPE


FUNCTION_BLOCK FB_OfflineParamEstimator
VAR_INPUT
    bExecute            : BOOL;

    // ---- 来自 FB_DataLogger 的聚合指标 ----
    bDataSufficient     : BOOL;
    iLoggedCycles       : INT;
    rRmsDecayRate       : REAL;        // 0 = 不变, 0.5 = 每周期减半
    rRmsSteadyMean      : REAL;
    rRmsSteadyStdDev    : REAL;
    rSyncToTrackRatio   : REAL;
    rRepeatability      : REAL;        // 0..1

    // ---- 当前ILC参数(用于增量调整)----
    rL_Current          : REAL;
    rLambda_Current     : REAL;
    rAlpha_Current      : REAL;

    // ---- 推荐参数范围(安全限位)----
    rL_Min              : REAL := 0.05;
    rL_Max              : REAL := 0.6;
    rLambda_Min         : REAL := 0.0;
    rLambda_Max         : REAL := 1.0;
    rAlpha_Min          : REAL := 0.85;
    rAlpha_Max          : REAL := 0.999;

    // ---- 目标(可调)----
    rTargetDecayRate    : REAL := 0.25;   // 目标每周期RMS降低25%
END_VAR
VAR_OUTPUT
    bDone               : BOOL;
    bFailed             : BOOL;

    rL_Recommended      : REAL;
    rLambda_Recommended : REAL;
    rAlpha_Recommended  : REAL;

    // 诊断输出
    stDiagL             : ST_EstimatorDiag;
    stDiagLambda        : ST_EstimatorDiag;
    stDiagAlpha         : ST_EstimatorDiag;
    rOverallConfidence  : REAL;
END_VAR
VAR
    bExecutePrev        : BOOL;
    rLAdj               : REAL;
    rLambdaAdj          : REAL;
    rAlphaAdj           : REAL;
    rDecayDeficit       : REAL;
END_VAR

// 诊断码定义(为方便单字 INT 传到 HMI,使用枚举式 INT)
// 1xx = L
//  100 = 衰减率达标,L保持
//  101 = 衰减太慢,L增大
//  102 = 衰减振荡,L减小
//  103 = 已收敛,L建议保持但可微调
//  190 = 数据不足
// 2xx = λ
//  200 = 同步误差小,λ适当
//  201 = 同步误差占比大,λ增大
//  202 = 跟踪占比大,λ可减小
//  290 = 数据不足
// 3xx = α
//  300 = 重复性高,α维持高位
//  301 = 重复性中等,α中等
//  302 = 重复性差,α降低对抗非重复扰动
//  390 = 数据不足

bDone := FALSE;
bFailed := FALSE;

IF bExecute AND NOT bExecutePrev THEN

    IF NOT bDataSufficient OR iLoggedCycles < 8 THEN
        bFailed := TRUE;
        stDiagL.iCode       := 190; stDiagL.rConfidence    := 0.0;
        stDiagL.sReason     := 'Data insufficient (need >= 8 cycles)';
        stDiagLambda.iCode  := 290; stDiagLambda.rConfidence := 0.0;
        stDiagLambda.sReason:= 'Data insufficient';
        stDiagAlpha.iCode   := 390; stDiagAlpha.rConfidence  := 0.0;
        stDiagAlpha.sReason := 'Data insufficient';
        rOverallConfidence  := 0.0;
        rL_Recommended      := rL_Current;
        rLambda_Recommended := rLambda_Current;
        rAlpha_Recommended  := rAlpha_Current;
    ELSE

        // ============================================================
        // 1. L (学习增益) 估计
        // ============================================================
        rDecayDeficit := rTargetDecayRate - rRmsDecayRate;

        IF rRmsDecayRate < 0.0 THEN
            // RMS反而上升 → 系统不稳定/学习超调
            rLAdj := rL_Current * 0.5;
            stDiagL.iCode       := 102;
            stDiagL.sReason     := 'RMS rising. Halve L for stability.';
            stDiagL.rConfidence := 0.9;
        ELSIF rRmsSteadyStdDev > 0.3 * rRmsSteadyMean THEN
            // 稳态抖动大 → L太大或Q滤波不够
            rLAdj := rL_Current * 0.7;
            stDiagL.iCode       := 102;
            stDiagL.sReason     := 'High oscillation in RMS. Reduce L by 30%.';
            stDiagL.rConfidence := 0.7;
        ELSIF rRmsSteadyMean < 0.05 THEN
            // 已经收敛得很好
            rLAdj := rL_Current;
            stDiagL.iCode       := 103;
            stDiagL.sReason     := 'Already converged. Keep L.';
            stDiagL.rConfidence := 0.95;
        ELSIF rRmsDecayRate < rTargetDecayRate * 0.5 THEN
            // 衰减太慢 → L偏小
            rLAdj := rL_Current * (1.0 + rDecayDeficit);
            stDiagL.iCode       := 101;
            stDiagL.sReason     := 'Slow convergence. Increase L.';
            stDiagL.rConfidence := 0.8;
        ELSE
            // 衰减接近目标
            rLAdj := rL_Current * (1.0 + rDecayDeficit * 0.5);
            stDiagL.iCode       := 100;
            stDiagL.sReason     := 'Decay rate near target. Minor tweak.';
            stDiagL.rConfidence := 0.85;
        END_IF

        // L 限幅
        IF rLAdj < rL_Min THEN rLAdj := rL_Min; END_IF
        IF rLAdj > rL_Max THEN rLAdj := rL_Max; END_IF
        rL_Recommended := rLAdj;

        // ============================================================
        // 2. λ (同步耦合) 估计
        // ============================================================
        IF rSyncToTrackRatio > 0.5 THEN
            // 同步误差占比大 → 需要强化同步耦合
            rLambdaAdj := rLambda_Current + 0.2;
            stDiagLambda.iCode       := 201;
            stDiagLambda.sReason     := 'Sync error large. Increase lambda.';
            stDiagLambda.rConfidence := 0.85;
        ELSIF rSyncToTrackRatio > 0.2 THEN
            // 同步误差中等
            rLambdaAdj := rLambda_Current + 0.1;
            stDiagLambda.iCode       := 201;
            stDiagLambda.sReason     := 'Sync error moderate. Bump lambda.';
            stDiagLambda.rConfidence := 0.7;
        ELSIF rSyncToTrackRatio < 0.05 AND rLambda_Current > 0.3 THEN
            // 同步误差已小,λ可减以加快跟踪学习
            rLambdaAdj := rLambda_Current - 0.1;
            stDiagLambda.iCode       := 202;
            stDiagLambda.sReason     := 'Sync OK. Reduce lambda for tracking.';
            stDiagLambda.rConfidence := 0.7;
        ELSE
            rLambdaAdj := rLambda_Current;
            stDiagLambda.iCode       := 200;
            stDiagLambda.sReason     := 'Sync ratio balanced. Keep lambda.';
            stDiagLambda.rConfidence := 0.9;
        END_IF

        IF rLambdaAdj < rLambda_Min THEN rLambdaAdj := rLambda_Min; END_IF
        IF rLambdaAdj > rLambda_Max THEN rLambdaAdj := rLambda_Max; END_IF
        rLambda_Recommended := rLambdaAdj;

        // ============================================================
        // 3. α (遗忘因子) 估计
        // ============================================================
        // 推荐:α = α_min + (α_max - α_min) · repeatability^2
        // 高重复性 → α 接近上限,允许积累纯ILC学习
        // 低重复性 → α 降低,防非重复扰动累积
        rAlphaAdj := rAlpha_Min + (rAlpha_Max - rAlpha_Min)
                   * rRepeatability * rRepeatability;

        IF rRepeatability > 0.9 THEN
            stDiagAlpha.iCode       := 300;
            stDiagAlpha.sReason     := 'High repeatability. Keep alpha high.';
            stDiagAlpha.rConfidence := 0.9;
        ELSIF rRepeatability > 0.6 THEN
            stDiagAlpha.iCode       := 301;
            stDiagAlpha.sReason     := 'Moderate repeatability. Mid alpha.';
            stDiagAlpha.rConfidence := 0.8;
        ELSE
            stDiagAlpha.iCode       := 302;
            stDiagAlpha.sReason     := 'Low repeatability. Lower alpha.';
            stDiagAlpha.rConfidence := 0.8;
        END_IF

        IF rAlphaAdj < rAlpha_Min THEN rAlphaAdj := rAlpha_Min; END_IF
        IF rAlphaAdj > rAlpha_Max THEN rAlphaAdj := rAlpha_Max; END_IF
        rAlpha_Recommended := rAlphaAdj;

        // ============================================================
        // 4. 整体置信度
        // ============================================================
        rOverallConfidence := (stDiagL.rConfidence
                            +  stDiagLambda.rConfidence
                            +  stDiagAlpha.rConfidence) / 3.0;
        // 数据较少时打折
        IF iLoggedCycles < 16 THEN
            rOverallConfidence := rOverallConfidence
                                * INT_TO_REAL(iLoggedCycles) / 16.0;
        END_IF

        bDone := TRUE;
    END_IF
END_IF
bExecutePrev := bExecute;

END_FUNCTION_BLOCK
