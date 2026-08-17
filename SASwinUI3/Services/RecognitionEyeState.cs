namespace SAS.Services;

internal sealed record RecognitionEyeState(bool Available, bool LeftOpen, bool RightOpen)
{
    public bool IsOpen => LeftOpen || RightOpen;
    public bool BothOpen => LeftOpen && RightOpen;
    public bool IsClosed => !LeftOpen && !RightOpen;
    public bool OneClosed => LeftOpen != RightOpen;
    public bool IsBlinkClosedCandidate => IsClosed || OneClosed;

    public string DisplayText => this switch
    {
        { LeftOpen: true, RightOpen: true } => "Eyes open",
        { LeftOpen: false, RightOpen: false } => "Eyes closed",
        { LeftOpen: true, RightOpen: false } => "Right eye closed",
        { LeftOpen: false, RightOpen: true } => "Left eye closed",
        _ => "Eye check unavailable"
    };
}
