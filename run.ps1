param(
    [Parameter(Mandatory=$true)][string]$File,
    [int]$Batch = 1,
    [switch]$StopOnError
)

# Check file existence
if (-not (Test-Path $File)) {
    Write-Host "File not found: $File" -ForegroundColor Red
    exit 1
}

# Read commands
$Commands = Get-Content $File
$NumCmds = $Commands.Count

# Status arrays
$Status = @()
$Jobs = @()
$ExitCodes = @()

for ($i = 0; $i -lt $NumCmds; $i++) {
    $Status += "WAITING"
    $Jobs += $null
    $ExitCodes += $null
}

function Print-Status {
    Clear-Host
    for ($i = 0; $i -lt $NumCmds; $i++) {
        $cmd = $Commands[$i]
        $shortCmd = if ($cmd.Length -gt 40) { $cmd.Substring(0,40) + "..." } else { $cmd }
        switch ($Status[$i]) {
            "WAITING"  { Write-Host "[WAITING]  $shortCmd" -ForegroundColor Yellow }
            "RUNNING"  { Write-Host "[RUNNING]  $shortCmd" -ForegroundColor White }
            "SUCCESS"  { Write-Host "[SUCCESS]  $shortCmd" -ForegroundColor Green }
            "FAIL"     { Write-Host "[FAIL]     $shortCmd | ExitCode: $($ExitCodes[$i])" -ForegroundColor Red }
        }
    }
}

Clear-Host
Print-Status

$runningCount = 0
$finished = 0

while ($finished -lt $NumCmds) {
    # Launch new commands if possible
    for ($i = 0; $i -lt $NumCmds; $i++) {
        if ($Status[$i] -eq "WAITING" -and $runningCount -lt $Batch) {
            $Status[$i] = "RUNNING"
            $Jobs[$i] = Start-Job -ScriptBlock { param($c) Invoke-Expression $c } -ArgumentList $Commands[$i]
            $runningCount++
        }
    }

    Print-Status

    # Check running commands
    for ($i = 0; $i -lt $NumCmds; $i++) {
        if ($Status[$i] -eq "RUNNING") {
            if ($Jobs[$i].State -eq "Completed") {
                $ExitCodes[$i] = $Jobs[$i].ExitCode
                if ($ExitCodes[$i] -eq 0) {
                    $Status[$i] = "SUCCESS"
                } else {
                    $Status[$i] = "FAIL"
                    if ($StopOnError) {
                        Print-Status
                        Write-Host "Stopped due to error in command: $($Commands[$i])" -ForegroundColor Red
                        # Stop all running jobs
                        foreach ($j in 0..($NumCmds-1)) {
                            if ($Status[$j] -eq "RUNNING") {
                                Stop-Job $Jobs[$j] -Force
                            }
                        }
                        exit 1
                    }
                }
                $runningCount--
                $finished++
                Print-Status
            }
        }
    }
    Start-Sleep -Milliseconds 100
}

Print-Status
