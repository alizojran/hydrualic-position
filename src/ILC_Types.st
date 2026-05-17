// ============================================================
// File   : ILC_Types.st
// 用途   : 多缸交叉耦合ILC的类型定义(枚举 + 结构体)
// 平台   : 自研CODESYS / 4核ARM 1.8GHz / RT-Linux
// ============================================================

// ---- 油缸耦合方式 ----
// INDEPENDENT  : 各缸独立工件,不引入同步误差耦合 (退化为并行ILC)
// RIGID_SYNC   : 同试件刚性多点加载,所有缸目标位置一致,
//                同步误差 = y_i - mean(y_active)
// PARALLEL_MECH: 并联机构(如Stewart平台),各缸有几何关系,
//                同步参考由用户通过 rSyncRef_arr 在线提供
TYPE E_ILC_CouplingMode :
(
    INDEPENDENT   := 0,
    RIGID_SYNC    := 1,
    PARALLEL_MECH := 2
);
END_TYPE


// ---- 运行状态机 ----
TYPE E_ILC_State :
(
    IDLE      := 0,    // 未使能
    WARMUP    := 1,    // 暖机期,前馈表不更新
    LEARNING  := 2,    // 学习中
    CONVERGED := 3,    // 已收敛
    FAULT     := 4     // 故障(同步误差越限/参数非法)
);
END_TYPE


// ---- 单通道统计输出 ----
TYPE ST_ILC_ChannelStats :
STRUCT
    rRmsTrackError : REAL;   // 跟踪误差RMS(上周期)
    rPeakTrackError: REAL;   // 跟踪误差峰值绝对值(上周期)
    rRmsSyncError  : REAL;   // 同步误差RMS(上周期)
    rPeakSyncError : REAL;   // 同步误差峰值绝对值(上周期)
    rMaxFF         : REAL;   // 前馈表最大绝对值(上周期)
    bChannelOK     : BOOL;   // 通道健康
END_STRUCT
END_TYPE
