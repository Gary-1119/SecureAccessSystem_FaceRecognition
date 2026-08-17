namespace SAS.Services;

internal sealed class SilentBlinkLivenessService
{
    private const int RequiredSilentBlinks = 1;
    private static readonly TimeSpan StableLiveMatchWindow = TimeSpan.FromSeconds(6);
    private static readonly TimeSpan BlinkCloseToOpenWindow = TimeSpan.FromMilliseconds(650);

    private DateTimeOffset _lastStableLiveMatchAt = DateTimeOffset.MinValue;
    private string _stableLiveEmployeeId = "";
    private int _stableLiveMatchCount;
    private bool _blinkSawOpen;
    private bool _blinkSawClosed;
    private int _blinkClosedCandidateCount;
    private bool _blinkSawBothClosed;
    private DateTimeOffset _blinkClosedCandidateAt = DateTimeOffset.MinValue;

    public SilentLivenessResult RecordBlink(string employeeId, RecognitionEyeState eyeState, DateTimeOffset now)
    {
        if (!string.Equals(_stableLiveEmployeeId, employeeId, StringComparison.OrdinalIgnoreCase) ||
            now - _lastStableLiveMatchAt > StableLiveMatchWindow ||
            !eyeState.Available)
        {
            _stableLiveEmployeeId = employeeId;
            _stableLiveMatchCount = 0;
            _blinkSawOpen = eyeState.BothOpen;
            _blinkSawClosed = false;
            _blinkClosedCandidateCount = 0;
            _blinkSawBothClosed = false;
            _blinkClosedCandidateAt = DateTimeOffset.MinValue;
            _lastStableLiveMatchAt = now;
            return new SilentLivenessResult(_stableLiveMatchCount, 0d, false, eyeState.Available ? eyeState.DisplayText : "Eye check unavailable");
        }

        _lastStableLiveMatchAt = now;
        if (eyeState.BothOpen)
        {
            if (_blinkSawOpen &&
                _blinkSawClosed &&
                now - _blinkClosedCandidateAt <= BlinkCloseToOpenWindow &&
                (_blinkSawBothClosed || _blinkClosedCandidateCount >= 2))
            {
                _stableLiveMatchCount++;
            }

            _blinkSawOpen = true;
            _blinkSawClosed = false;
            _blinkClosedCandidateCount = 0;
            _blinkSawBothClosed = false;
            _blinkClosedCandidateAt = DateTimeOffset.MinValue;
        }

        if (_blinkSawOpen && eyeState.IsBlinkClosedCandidate)
        {
            if (!_blinkSawClosed || now - _blinkClosedCandidateAt > BlinkCloseToOpenWindow)
            {
                _blinkSawClosed = true;
                _blinkClosedCandidateCount = 1;
                _blinkSawBothClosed = eyeState.IsClosed;
                _blinkClosedCandidateAt = now;
            }
            else
            {
                _blinkClosedCandidateCount++;
                _blinkSawBothClosed |= eyeState.IsClosed;
            }
        }

        if (_blinkSawClosed && now - _blinkClosedCandidateAt > BlinkCloseToOpenWindow)
        {
            _blinkSawClosed = false;
            _blinkClosedCandidateCount = 0;
            _blinkSawBothClosed = false;
            _blinkClosedCandidateAt = DateTimeOffset.MinValue;
        }

        var score = _stableLiveMatchCount >= RequiredSilentBlinks
            ? 100d
            : Math.Clamp(_stableLiveMatchCount * 100d / RequiredSilentBlinks, 0d, 100d);
        return new SilentLivenessResult(_stableLiveMatchCount, score, _stableLiveMatchCount >= RequiredSilentBlinks, eyeState.DisplayText);
    }

    public void Reset()
    {
        _stableLiveEmployeeId = "";
        _stableLiveMatchCount = 0;
        _blinkSawOpen = false;
        _blinkSawClosed = false;
        _blinkClosedCandidateCount = 0;
        _blinkSawBothClosed = false;
        _blinkClosedCandidateAt = DateTimeOffset.MinValue;
        _lastStableLiveMatchAt = DateTimeOffset.MinValue;
    }
}
