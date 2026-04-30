param (
    [Parameter(Mandatory=$true, Position=0)]
    [ValidateSet("handson", "solution")]
    [string]$Mode
)

# Set active mode
$Mode | Out-File -FilePath ".active_mode" -Encoding utf8 -NoNewline

# Note: In Windows, stopping the process might require more complex logic
# but for a workshop context, this indicates the intended mode change.
Write-Host "--- Switching to $Mode mode ---"
python run_demo.py
