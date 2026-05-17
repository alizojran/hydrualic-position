// ============================================================
// File   : FB_SimplePID.st
// 用途   : 位置环PID(供仿真使用);抗积分饱和,反归一化输出
// ============================================================

FUNCTION_BLOCK FB_SimplePID
VAR_INPUT
    rSetpoint : REAL;
    rFeedback : REAL;
    rKp       : REAL := 0.05;
    rKi       : REAL := 1.0;
    rKd       : REAL := 0.0;
    rTs       : REAL := 0.001;
    rOutMax   : REAL :=  1.0;
    rOutMin   : REAL := -1.0;
    bEnable   : BOOL := TRUE;
    bReset    : BOOL := FALSE;
END_VAR
VAR_OUTPUT
    rOutput   : REAL;
END_VAR
VAR
    rErr      : REAL;
    rErrPrev  : REAL;
    rIntTerm  : REAL;
    rPreSat   : REAL;
END_VAR

IF bReset THEN
    rIntTerm := 0.0;
    rErrPrev := 0.0;
END_IF

IF NOT bEnable THEN
    rOutput := 0.0;
    rIntTerm := 0.0;
    rErrPrev := rSetpoint - rFeedback;
    RETURN;
END_IF

rErr := rSetpoint - rFeedback;

// 积分项(反饱和:先更新,后限幅)
rIntTerm := rIntTerm + rKi * rErr * rTs;
IF rIntTerm >  rOutMax THEN rIntTerm :=  rOutMax; END_IF
IF rIntTerm <  rOutMin THEN rIntTerm :=  rOutMin; END_IF

rPreSat := rKp * rErr + rIntTerm + rKd * (rErr - rErrPrev) / rTs;

IF rPreSat > rOutMax THEN
    rOutput := rOutMax;
    // 反算积分(简化反饱和)
    rIntTerm := rIntTerm - (rPreSat - rOutMax);
ELSIF rPreSat < rOutMin THEN
    rOutput := rOutMin;
    rIntTerm := rIntTerm - (rPreSat - rOutMin);
ELSE
    rOutput := rPreSat;
END_IF

rErrPrev := rErr;
END_FUNCTION_BLOCK
