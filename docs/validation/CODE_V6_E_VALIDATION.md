# CODE V6-E Validation — Spectral, Partial, and Hybrid Reconstruction

## Stage identity

```text
Project : W-MWXT-WAVETABLE-TOOL
Stage   : CODE V6-E
Branch  : code-v6-cycle-engine
Version : 0.5.0 (unchanged until CODE V6-F)
```

## Delivered contract

CODE V6-E converts the accepted CODE V6-D `SelectedCycleSet` into deterministic,
float-domain reconstructed waves. It preserves the complete V6-A through V6-D hash
chain and never modifies the imported source audio.

Public models and functions:

```text
ReconstructionStrategy
ReconstructionDecision
ReconstructedWave
ReconstructedWaveSet
reconstruct_selected_cycles
analyze_audio_source_reconstruction
```

## Strategies

```text
auto      choose spectral, partial, or hybrid per selected V6-C candidate
spectral  retain every representable source-cycle spectral bin
partial   retain the strongest configured harmonic bins
hybrid    blend periodic time-domain interpolation with dominant partials
```

Automatic strategy selection is deterministic:

```text
spectral  seam >= 0.80 and spectral consistency >= 0.90
partial   periodicity >= 0.90 and energy consistency >= 0.80
hybrid    all other selected candidates
```

## Float-domain waveform contract

Default reconstruction settings:

```text
target sample count : 128
maximum partials    : 32
hybrid time weight  : 0.35
normalization peak  : 0.98
remove DC           : yes
```

The 128-point default matches the logical Microwave XT User Wave resolution, but
CODE V6-E does not quantize samples to the hardware's 8-bit representation. Every
sample remains a deterministic finite float. Hardware quantization and SysEx output
remain outside this stage.

Each `ReconstructedWave` records:

```text
V6-C candidate index and SHA-256
V6-D ranking SHA-256
source-cycle sample bounds and SHA-256
concrete reconstruction strategy
retained harmonic-bin count
normalization gain
source and reconstructed RMS
peak amplitude
seam value and slope errors
seam score
spectral similarity score
complete reconstructed float sample payload
wave SHA-256
```

## Hash chain

```text
CycleDiscoveryAnalysis.analysis_sha256
    └── SelectedCycleSet.analysis_sha256
            └── ReconstructedWaveSet.analysis_sha256
                    └── ReconstructedWave.wave_sha256
```

The selected candidate indexes, candidate hashes, and ranking hashes in the wave set
must exactly match the order of the reconstructed waves.

## CLI

Automatic reconstruction:

```powershell
W-MWXT-WAVETABLE-TOOL reconstruct-waves `
  "D:\Audio\source.wav" `
  --reconstruction-strategy auto `
  --target-sample-count 128 `
  --maximum-partials 32 `
  --report "D:\Reports\source.reconstruction.json"
```

Explicit partial reconstruction:

```powershell
W-MWXT-WAVETABLE-TOOL reconstruct-waves `
  "D:\Audio\source.wav" `
  --reconstruction-strategy partial `
  --maximum-partials 24 `
  --normalization-peak 0.98 `
  --report "D:\Reports\source.partial.json"
```

## Safety boundary

CODE V6-E does not:

- modify, trim, normalize, resample, or overwrite source audio;
- write reconstructed audio files;
- quantize float waves to Microwave XT 8-bit values;
- allocate User Wave or User Wavetable destinations;
- build SysEx;
- transmit MIDI;
- execute any irreversible operation.

The normalization recorded by this stage applies only to the in-memory reconstructed
float payload. The source remains byte-identical.

## Targeted validation

```text
Core reconstruction tests : 48
CLI tests                 : 5
Public API tests          : 5
Targeted total            : 58
```

## Acceptance gate

CODE V6-E passes when:

1. all 58 targeted tests pass;
2. the public and private complete suites pass;
3. two real-audio reconstruction reports are byte-identical;
4. source audio remains unchanged;
5. every V6-C, V6-D, candidate, ranking, source-cycle, wave, and aggregate hash link
   validates;
6. every reconstructed payload has the configured sample count and finite values;
7. peak, DC, retained-bin, seam, and strategy contracts hold;
8. selected cycle order is preserved exactly;
9. no generated report, audio, or private dump enters Git.
