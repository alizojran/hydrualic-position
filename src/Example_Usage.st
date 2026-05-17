// ============================================================
// File   : Example_Usage.st
// 用途   : FB_CrossCoupledILC 三种耦合模式的使用示例
// 平台   : 自研CODESYS / 4核ARM 1.8GHz / RT-Linux
// ============================================================

// ============================================================
// 示例1:4缸独立工件 — 4台独立疲劳试验机共享1套学习算法
// ============================================================
PROGRAM PRG_Example_Independent
VAR
    fbILC          : FB_CrossCoupledILC;
    aPosCmd        : ARRAY[1..200] OF REAL;
    aVelCmd        : ARRAY[1..200] OF REAL;
    aPosFb         : ARRAY[1..200] OF REAL;
    aSyncRef       : ARRAY[1..200] OF REAL;
    aChEnable      : ARRAY[1..200] OF BOOL;
    aPosCmdOut     : ARRAY[1..200] OF REAL;

    iPhase         : INT;       // 来自SoftMotion主时钟
    bNewCycle      : BOOL;
    iPtsPerCycle   : INT := 1000;   // 1秒 @ 1kHz
END_VAR

// 初始化(只跑一次)
aChEnable[1] := TRUE;
aChEnable[2] := TRUE;
aChEnable[3] := TRUE;
aChEnable[4] := TRUE;

// 每个RT周期调用
fbILC(
    bEnable          := TRUE,
    bReset           := FALSE,
    iNumCylinders    := 4,
    iPointsPerCycle  := iPtsPerCycle,
    eCouplingMode    := E_ILC_CouplingMode.INDEPENDENT,
    iPointIndex      := iPhase,
    bNewCycle        := bNewCycle,
    rPosCmd_arr      := aPosCmd,
    rVelCmd_arr      := aVelCmd,
    rPosFb_arr       := aPosFb,
    bChannelEnable   := aChEnable,
    rSyncRef_arr     := aSyncRef,        // 独立模式不用
    rLearningGain    := 0.3,
    rSyncCoupling    := 0.0,             // 独立模式λ设为0
    rForgetting      := 0.98,
    rFF_Limit        := 5.0,             // ±5mm前馈限幅
    rConvergeTol     := 0.05,            // 0.05mm RMS视为收敛
    rSafetyTol       := 10.0,            // 独立模式同步容差宽
    nWarmupCycles    := 3,
    iPhaseLead       := 2,
    rQFilterStrength := 0.5,
    iUpdateChunkSize := 0,               // 4缸不分块
    rILC_FF_arr      => ,
    rPosCmdOut_arr   => aPosCmdOut
);
// aPosCmdOut[1..4] 送到各缸位置环PID的setpoint
END_PROGRAM


// ============================================================
// 示例2:6缸刚性多点加载 — 同一试件6点同步压制
//        要求:6缸位置反馈严格一致,任一缸偏差 > 0.3mm 触发停机
// ============================================================
PROGRAM PRG_Example_RigidSync
VAR
    fbILC          : FB_CrossCoupledILC;
    aPosCmd        : ARRAY[1..200] OF REAL;
    aVelCmd        : ARRAY[1..200] OF REAL;
    aPosFb         : ARRAY[1..200] OF REAL;
    aSyncRef       : ARRAY[1..200] OF REAL;
    aChEnable      : ARRAY[1..200] OF BOOL;
    aPosCmdOut     : ARRAY[1..200] OF REAL;

    iPhase         : INT;
    bNewCycle      : BOOL;
    iPtsPerCycle   : INT := 500;        // 0.5秒 @ 1kHz
    bSafetyReset   : BOOL;
    i              : INT;
END_VAR

FOR i := 1 TO 6 DO aChEnable[i] := TRUE; END_FOR

fbILC(
    bEnable          := TRUE,
    bReset           := bSafetyReset,
    iNumCylinders    := 6,
    iPointsPerCycle  := iPtsPerCycle,
    eCouplingMode    := E_ILC_CouplingMode.RIGID_SYNC,
    iPointIndex      := iPhase,
    bNewCycle        := bNewCycle,
    rPosCmd_arr      := aPosCmd,
    rVelCmd_arr      := aVelCmd,
    rPosFb_arr       := aPosFb,
    bChannelEnable   := aChEnable,
    rSyncRef_arr     := aSyncRef,        // 刚性同步模式不用,内部用mean(y)
    rLearningGain    := 0.25,
    rSyncCoupling    := 0.8,             // 强同步耦合
    rForgetting      := 0.99,
    rFF_Limit        := 2.0,             // 刚性场景前馈应保守
    rConvergeTol     := 0.02,            // 0.02mm RMS
    rSafetyTol       := 0.3,             // 任一缸偏差>0.3mm触发故障
    nWarmupCycles    := 5,               // 多暖机几周期,统计更稳
    iPhaseLead       := 3,
    rQFilterStrength := 0.6,             // 滤波稍强,抗共振
    iUpdateChunkSize := 0,               // 6缸不分块
    rILC_FF_arr      => ,
    rPosCmdOut_arr   => aPosCmdOut
);

// 如果触发故障,机械上应立即转为各缸独立PID或泄压停机
// IF fbILC.bFault THEN ... END_IF
END_PROGRAM


// ============================================================
// 示例3:并联机构 — 6自由度Stewart平台,6缸由位姿运动学决定目标
//        每缸目标位置不同,但缸间有精确几何关系
// ============================================================
PROGRAM PRG_Example_ParallelMech
VAR
    fbILC          : FB_CrossCoupledILC;
    aPosCmd        : ARRAY[1..200] OF REAL;
    aVelCmd        : ARRAY[1..200] OF REAL;
    aPosFb         : ARRAY[1..200] OF REAL;
    aSyncRef       : ARRAY[1..200] OF REAL;
    aChEnable      : ARRAY[1..200] OF BOOL;
    aPosCmdOut     : ARRAY[1..200] OF REAL;

    iPhase         : INT;
    bNewCycle      : BOOL;
    iPtsPerCycle   : INT := 2000;
    i              : INT;
END_VAR

FOR i := 1 TO 6 DO aChEnable[i] := TRUE; END_FOR

// 关键:上层运动学逆解模块根据当前位姿计算每缸的"理论位置",
//      该值送到 aSyncRef[1..6],作为各缸的同步参考
// 例如:Stewart平台位姿 (x,y,z,roll,pitch,yaw) → 6缸长度
//      使用通用 Inverse Kinematics 函数块计算
// fbStewartIK(rPose := stPose, rLegLength => aSyncRef);

fbILC(
    bEnable          := TRUE,
    bReset           := FALSE,
    iNumCylinders    := 6,
    iPointsPerCycle  := iPtsPerCycle,
    eCouplingMode    := E_ILC_CouplingMode.PARALLEL_MECH,
    iPointIndex      := iPhase,
    bNewCycle        := bNewCycle,
    rPosCmd_arr      := aPosCmd,
    rVelCmd_arr      := aVelCmd,
    rPosFb_arr       := aPosFb,
    bChannelEnable   := aChEnable,
    rSyncRef_arr     := aSyncRef,        // 由运动学逆解填充
    rLearningGain    := 0.2,
    rSyncCoupling    := 0.5,
    rForgetting      := 0.98,
    rFF_Limit        := 3.0,
    rConvergeTol     := 0.03,
    rSafetyTol       := 1.0,
    nWarmupCycles    := 5,
    iPhaseLead       := 2,
    rQFilterStrength := 0.5,
    iUpdateChunkSize := 0,
    rILC_FF_arr      => ,
    rPosCmdOut_arr   => aPosCmdOut
);
END_PROGRAM


// ============================================================
// 示例4:200缸大规模刚性同步 — 分块更新避免阻塞RT
// ============================================================
PROGRAM PRG_Example_LargeScale
VAR
    fbILC          : FB_CrossCoupledILC;
    aPosCmd        : ARRAY[1..200] OF REAL;
    aVelCmd        : ARRAY[1..200] OF REAL;
    aPosFb         : ARRAY[1..200] OF REAL;
    aSyncRef       : ARRAY[1..200] OF REAL;
    aChEnable      : ARRAY[1..200] OF BOOL;
    aPosCmdOut     : ARRAY[1..200] OF REAL;

    iPhase         : INT;
    bNewCycle      : BOOL;
    iPtsPerCycle   : INT := 2000;
    i              : INT;
END_VAR

FOR i := 1 TO 200 DO aChEnable[i] := TRUE; END_FOR

// 200缸 × 2000点FF表更新 ≈ 400K运算 ≈ 2-3ms@1.8GHz ARM
// 若RT周期1ms,单次完成会丢失2-3次循环 → 分块,每次10缸
// 200/10 = 20次循环完成更新,即20ms,适合周期>=50ms的脉冲

fbILC(
    bEnable          := TRUE,
    bReset           := FALSE,
    iNumCylinders    := 200,
    iPointsPerCycle  := iPtsPerCycle,
    eCouplingMode    := E_ILC_CouplingMode.RIGID_SYNC,
    iPointIndex      := iPhase,
    bNewCycle        := bNewCycle,
    rPosCmd_arr      := aPosCmd,
    rVelCmd_arr      := aVelCmd,
    rPosFb_arr       := aPosFb,
    bChannelEnable   := aChEnable,
    rSyncRef_arr     := aSyncRef,
    rLearningGain    := 0.2,
    rSyncCoupling    := 0.6,
    rForgetting      := 0.98,
    rFF_Limit        := 2.0,
    rConvergeTol     := 0.05,
    rSafetyTol       := 0.5,
    nWarmupCycles    := 10,              // 大规模慢起步
    iPhaseLead       := 2,
    rQFilterStrength := 0.5,
    iUpdateChunkSize := 10,              // ★ 每个RT周期只更新10缸
    rILC_FF_arr      => ,
    rPosCmdOut_arr   => aPosCmdOut
);
END_PROGRAM
