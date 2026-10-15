# Generate a spoken sample meeting recording using Windows built-in TTS.
# Creates apps\api\tests\sample-meeting.wav
#
# Usage: powershell -ExecutionPolicy Bypass -File apps\api\tests\make-sample-audio.ps1

$ErrorActionPreference = "Stop"

Add-Type -AssemblyName System.Speech

$outDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$outFile = Join-Path $outDir "sample-meeting.wav"

$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer

# Pick an installed voice
$voice = $synth.GetInstalledVoices() | Where-Object { $_.Enabled } | Select-Object -First 1
if ($voice) {
    $synth.SelectVoice($voice.VoiceInfo.Name)
    Write-Host "Voice: $($voice.VoiceInfo.Name)"
}

$synth.Rate = 0

$lines = @(
    "Okay team, let's start the sprint planning meeting.",
    "First decision: we will ship the login page by Friday.",
    "Second decision: Google authentication must be added this sprint.",
    "Priya will redesign the dashboard layout.",
    "Rahul will finish the login page and write the tests.",
    "There is a risk that testing starts late and blocks the release.",
    "Open question: who will own the production deployment?",
    "Next steps: daily standup at ten a m, and a demo on Monday."
)

$text = $lines -join " "
$synth.SetOutputToWaveFile($outFile)
$synth.Speak($text)
$synth.SetOutputToNull()
$synth.Dispose()

Write-Host "Wrote $outFile"
Write-Host ("Size: " + [math]::Round((Get-Item $outFile).Length / 1KB, 1) + " KB")
