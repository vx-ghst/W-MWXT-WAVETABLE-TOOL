# CODE V8-0B Validation - Import, signal, behavior, and regions

## Stage identity

```text
Project : W-MWXT-WAVETABLE-TOOL
Stage   : CODE V8-0B
Branch  : code-v8-wavetable-builder
Base    : CODE V8-0A / 820927bfdd69dbac55ae3fdf9a90f0d7c716f50c
Version : 0.7.0 (unchanged until CODE V8-G)
Status  : VALIDATED - LOCAL, PRIVATE, WHEEL, AND REMOTE CI GATES PASSED
```

## Closed requirements

```text
CDC-IMP-006  complete deterministic mono policies
CDC-SIG-003  dedicated rapid frequency-modulation analysis
CDC-SIG-010  complete time-varying saturation analysis
CDC-SIG-011  explicit asymmetry, density, and complexity metrics
CDC-SIG-013  close-fundamental, beating, unison, and detune analysis
CDC-SIG-015  eight required source-behavior classes
CDC-REG-001  eight required active region classes plus explicit silence
CDC-REG-003  useful spectral-change scoring
CDC-REG-004  long low-change redundancy detection
CDC-REG-005  deterministic interest-weighted allocation
```

## Mono contract

`MonoPolicy` now contains the complete public policy set:

```text
auto
sum
average
left
right
mid
best_periodicity
first_channel
dominant_channel
```

`FIRST_CHANNEL` and `DOMINANT_CHANNEL` remain compatibility policies. `AUTO` applies the established safety gates in this order:

1. mono passthrough;
2. only active channel;
3. identical channels;
4. destructive anti-phase protection;
5. decisive periodicity comparison when sample rate is available;
6. deterministic arithmetic-average fallback.

Best-periodicity decisions record every candidate score, the selected candidate, the winning margin, channel RMS values, stereo correlation, and a normalized reason. The candidate order is canonical and provides the final tie-break.

## Signal-extension contract

The accepted CODE V4 `SignalAnalysis` remains unchanged. V8-0B adds `SignalExtensionAnalysis` schema 1 with exact links to:

```text
SignalAnalysis.analysis_sha256
PitchPeriodicityAnalysis.analysis_sha256
sample SHA-256
sample rate
sample count
```

Its four components are:

```text
FrequencyModulationAnalysis
SaturationAnalysis
ComplexityAnalysis
BeatingAnalysis
```

All component models reject non-finite values and serialize with `allow_nan=False` compatible payloads and deterministic SHA-256 values.

## Rapid-FM contract

Rapid FM is measured from voiced pitch frames after deterministic slow-trend removal. The contract records:

```text
original pitch-frame indexes
reference frequency
per-frame deviation in cents
per-frame rapid component in cents
rapid RMS and peak-to-peak depth
estimated modulation rate
bounded rapid-FM score
confidence
detection decision and reason
```

Sparse voiced grids preserve their original frame indexes. Sources without voiced frames return an explicit zero-evidence result rather than an exception.

## Saturation contract

Saturation is measured over deterministic overlapping frames. Each frame records:

```text
RMS and absolute peak
crest factor
clipped ratio
near-clip ratio
flat-extreme ratio
signed peak asymmetry
bounded saturation score
```

The aggregate records mean, maximum, time variation, saturated-frame ratio, global asymmetry, the configured detection threshold, and an explicit decision reason. Silence produces a zero saturation score.

## Asymmetry, density, and complexity contract

`ComplexityAnalysis` records:

```text
signed positive/negative energy asymmetry
zero-crossing density
active-sample density
occupied spectral-bin density
normalized spectral entropy
temporal-difference density
density score
complexity score
```

Long inputs use a deterministic bounded center slice for the metric calculation while retaining the full-source sample hash and full-source sample count. The slice start, slice length, maximum length, and thresholds are serialized.

## Beating, unison, and detune contract

`BeatingAnalysis` uses deterministic windowed FFT peak detection and parabolic bin refinement. It records:

```text
primary frequency
secondary close frequency
beat rate in hertz
detune in cents
secondary-to-primary magnitude ratio
confidence
close-fundamental decision
unison decision
reason
```

Silence and single-tone cases return explicit no-pair results.

## Eight-behavior contract

The new V8 behavior layer contains exactly:

```text
periodic
quasi_periodic
evolving
pitch_variable
transient
noisy
non_periodic
hybrid
```

Every classification contains all eight raw and normalized scores in canonical order, one explanation per score, evidence values, confidence, ambiguity, a selected behavior, and a deterministic hash. Silence is explicitly represented as `non_periodic`; no unsupported ninth behavior is introduced.

The historical CODE V5 six-class `SourceClassification` remains unchanged.

## Region-interest contract

The historical V6 segmentation remains unchanged and is mapped into a V8 region layer containing:

```text
attack
establishment
sustain
evolution
saturation
redundancy
disappearance
noise
```

`silence` remains an explicit coverage state. Regions:

- cover the complete source;
- are contiguous and non-overlapping;
- link to the source, signal aggregate, signal extension, and segmentation hashes;
- record useful-change, redundancy, saturation, complexity, interest, and allocation scores;
- split a long low-flux sustain into one representative sustain and one redundant tail;
- allocate advisory slots with deterministic largest-remainder rounding by interest rather than time.

The allocation is advisory and does not perform the final CODE V8 wavetable build.

## Pathological-case repair

The autocorrelation pitch selector previously assumed that a positive local maximum always existed. Sparse transient frames can contain local maxima that are all non-positive, leaving the strong-candidate set empty. V8-0B now selects the deterministic highest local maximum in that case. Positive-score behavior is unchanged.

## Project compatibility

New projects persist structured mono periodicity evidence. The strict parser accepts complete legacy mono reports and complete extended mono reports. Partial or unknown representations are rejected. Round-trip and persistence tests cover both forms.

## Final validation evidence

```text
compileall                              : PASS
pip check                               : PASS
V8-0B targeted suite                    : 161 passed
Complete public suite                   : 1128 passed, 4 skipped
Complete private suite                  : 1132 passed
Project legacy/extended compatibility   : PASS
Known synthetic and real-signal corpus  : PASS
Sparse transient pathological case      : PASS
No NaN or infinity serialization        : PASS
Deterministic hashes                    : PASS
Isolated PEP 517 wheel build             : PASS
Wheel module inclusion                  : PASS
Wheel size                              : 288488 bytes
Wheel SHA-256                           : 3fb8af406c1bf0df78fa377ff70d1fe2ef5454959bd77fb00dca247561f19c64
git diff --check                        : PASS
```

The four public skips are exclusively the existing private real-dump tests. The complete private suite was executed with all four reference dumps mounted and finished with zero failed and zero skipped tests.

The wheel was built with the standard isolated PEP 517 process declared by `pyproject.toml`. Every new V8-0B package module was present in the generated wheel.

## Remote validation evidence

```text
Implementation commit       : 4d5eb6a61f2abf41a50a556e08f6ec5e1bbff630
Draft pull request          : 7
Pull-request base           : main
Pull-request head           : code-v8-wavetable-builder
Push workflow run           : 30813514420
Pull-request workflow run   : 30813516910
Unique CI environments      : 6
Push checks                 : 6/6 passed
Pull-request checks         : 6/6 passed
Total implementation checks : 12/12 passed
Cancelled                   : 0
Failed                      : 0
Skipped                     : 0
Pending                     : 0
```

The six operating-system and Python combinations ran through both push and pull-request events. Every job completed project installation, compileall, pip check, and the complete public suite.

## Closure gates

```text
[x] complete deterministic mono policies implemented
[x] rapid frequency-modulation analysis implemented
[x] saturation, asymmetry, density, and complexity metrics implemented
[x] beating, unison, and detune analysis implemented
[x] exactly eight source-behavior classes implemented
[x] region-interest contract covers the complete source
[x] long low-change redundancy detection implemented
[x] deterministic interest-weighted allocation implemented
[x] legacy and extended project representations validated
[x] sparse transient pathological case repaired
[x] all models reject NaN and infinity
[x] deterministic serialization and hashes validated
[x] targeted V8-0B suite passes
[x] complete public suite passes
[x] complete private suite passes with all four reference dumps
[x] isolated PEP 517 wheel builds successfully
[x] all new package modules are present in the wheel
[x] twelve implementation checks pass
[x] implementation commit SHA is recorded
[x] repository is clean after the implementation commit
[x] no automatic MIDI or SysEx transmission is introduced
[x] no private dump, generated SysEx, audio capture, or private evidence is committed
```

CODE V8-0B is formally closed.

This closure validates V8-0B only. It does not claim implementation of V8-0C spectrum, perceptual, musical-classification, or conversion-mode requirements.

## Safety boundary

CODE V8-0B opens no MIDI port, transmits no SysEx, modifies no instrument state, and commits no private dump, generated SysEx, audio capture, local absolute path, or private evidence file.
