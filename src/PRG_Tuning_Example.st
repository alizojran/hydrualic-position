// ============================================================
// File   : PRG_Tuning_Example.st
// 用途   : 演示如何用 FB_PhaseLeadTuner 在ILC启动前自动整定 iPhaseLead
//
// 流程:
//   1. 选定要整定的缸(eTuneState=0 → 1)
//   2. 该缸位置环切换到 fbTuner.rStepCmdOut(其他缸保持静止)
//   3. fbTuner 完成测量,输出 iEstLeadPts
//   4. 将估计值写入 ILC 的 iPhaseLead,启动正常运行
//
// 多缸整定: 通常对1~2缸执行整定足够(同型号阀+缸,系统延迟近似)
//          若各缸差异大,可循环对每缸整定取平均值
// ============================================================

PROGRAM PRG_Tuning_Example
VAR
    // ---- 整定器 ----
    fbTuner             : FB_PhaseLeadTuner;
    // ---- 仿真用,实际项目改成真实位置反馈+伺服阀输出 ----
    fbPlantTune         : FB_PlantSim;
    fbPIDTune           : FB_SimplePID;
    rValveCmdTune       : REAL;
    rPosFbTune          : REAL;

    // ---- 整定状态机 ----
    eTuneState          : INT := 0;    // 0=IDLE,1=TUNING,2=APPLY,3=RUN_ILC
    bStartTune          : BOOL;
    iEstLeadFromTuner   : INT;
    rEstTauFromTuner    : REAL;
    rEstDelayFromTuner  : REAL;

    // ---- ILC 参数(整定后填入)----
    iPhaseLeadForILC    : INT := 10;   // 默认值,整定后被覆盖

    // ---- 仿真参数 ----
    rTs                 : REAL := 0.001;
    bInit               : BOOL := FALSE;
END_VAR

// 初始化仿真被控对象
IF NOT bInit THEN
    fbPlantTune.rValveTC     := 0.012;
    fbPlantTune.rPureDelay_s := 0.006;
    fbPlantTune.rGain        := 100.0;
    fbPlantTune.rPosInit     := 100.0;
    fbPlantTune.bReset       := TRUE;
    bInit := TRUE;
END_IF
IF fbPlantTune.bReset THEN fbPlantTune.bReset := FALSE; END_IF

// ============================================================
// 整定状态机
// ============================================================
CASE eTuneState OF

0:  // IDLE — 等用户置位 bStartTune
    IF bStartTune THEN
        eTuneState := 1;
    END_IF

1:  // TUNING — 调用 tuner
    fbTuner(
        bStart       := TRUE,
        bAbort       := FALSE,
        rTs          := rTs,
        rPosFb       := rPosFbTune,
        rStepSize    := 5.0,
        rSettleTol   := 0.05,
        iSettlePts   := 200,
        iMaxMeasPts  := 3000
    );

    // 整定期间:把 tuner 的输出指令送到位置环
    fbPIDTune(
        rSetpoint := fbTuner.rStepCmdOut,
        rFeedback := rPosFbTune,
        rKp       := 0.04,
        rKi       := 1.0,
        rTs       := rTs,
        rOutMax   :=  1.0,
        rOutMin   := -1.0,
        rOutput   => rValveCmdTune
    );

    fbPlantTune(rValveCmd := rValveCmdTune, rTs := rTs, rPosOut => rPosFbTune);

    IF fbTuner.bDone THEN
        iEstLeadFromTuner  := fbTuner.iEstLeadPts;
        rEstTauFromTuner   := fbTuner.rEstTau_s;
        rEstDelayFromTuner := fbTuner.rEstDelay_s;
        iPhaseLeadForILC   := iEstLeadFromTuner;     // ★ 应用到ILC
        bStartTune         := FALSE;
        eTuneState         := 2;
    ELSIF fbTuner.bFailed THEN
        bStartTune := FALSE;
        eTuneState := 0;                              // 失败回到IDLE,留默认值
    END_IF

2:  // APPLY — 整定完成,可在此触发ILC启动(eTuneState=3)
    //          或显示在HMI待操作员确认
    IF bStartTune THEN
        // 再次整定
        eTuneState := 1;
    END_IF
    // 关闭tuner输出
    fbTuner(bStart := FALSE, bAbort := TRUE);

3:  // RUN_ILC — 实际ILC运行(此程序仅占位,详见 PRG_ILC_Simulation.st)
    ;

END_CASE

END_PROGRAM
