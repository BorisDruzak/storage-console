# Read-only, bounded and sanitized. No auditpol /set, SACL writes, GPO or file operations.
param([string]$ApprovedPilotRoot)
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
$result = [ordered]@{ mode = 'READ_ONLY'; observed_at = [DateTime]::UtcNow.ToString('o') }
try {
    $log = Get-WinEvent -ListLog Security
    $result.security_readable = $true
    $result.security_enabled = $log.IsEnabled
    $result.maximum_bytes = $log.MaximumSizeInBytes
    $result.retention = [string]$log.LogMode
    $result.record_count = $log.RecordCount
    $newest = Get-WinEvent -LogName Security -MaxEvents 1
    $oldest = Get-WinEvent -LogName Security -Oldest -MaxEvents 1
    $result.oldest_record_id = $oldest.RecordId
    $result.newest_record_id = $newest.RecordId
    $result.retained_seconds = [math]::Max(0, ($newest.TimeCreated - $oldest.TimeCreated).TotalSeconds)
    $recent = @(Get-WinEvent -FilterHashtable @{
        LogName = 'Security'; Id = @(4663,4660,4624,1102)
        StartTime = (Get-Date).AddMinutes(-5)
    } -MaxEvents 5000 -ErrorAction SilentlyContinue)
    $result.five_minute_count_capped = $recent.Count
    $result.rate_lower_bound_only = ($recent.Count -eq 5000)
    $result.event_counts = @{}
    foreach ($id in @(4663,4660,4624,1102)) {
        $result.event_counts[[string]$id] = @($recent | Where-Object Id -eq $id).Count
    }
} catch {
    $result.security_readable = $false
    $result.security_error = 'READ_FAILED'
}
$result.audit_policy = @{}
foreach ($entry in @(
    @{name='FILE_SYSTEM'; guid='{0CCE921D-69AE-11D9-BED3-505054503030}'}
    @{name='LOGON'; guid='{0CCE9215-69AE-11D9-BED3-505054503030}'}
)) {
    try {
        $raw = & auditpol.exe /get "/subcategory:$($entry.guid)" /r
        if ($LASTEXITCODE -ne 0) { throw 'READ_FAILED' }
        # CSV output varies by locale; expose only the two policy settings, not host/name.
        $rows = @($raw | ConvertFrom-Csv)
        $values = @($rows[-1].PSObject.Properties.Value)
        $result.audit_policy[$entry.name] = @($values[-2], $values[-1])
    } catch { $result.audit_policy[$entry.name] = @('UNKNOWN') }
}
$result.gpo_owner = 'OPERATOR_CONFIRMATION_REQUIRED'
$result.pilot_sacl = 'NO_APPROVED_PILOT_ROOT'
if ($ApprovedPilotRoot) {
    try {
        $acl = Get-Acl -LiteralPath $ApprovedPilotRoot -Audit
        $result.pilot_sacl = if ($acl.Audit.Count -gt 0) {'PRESENT_REQUIRES_SCOPE_REVIEW'} else {'ABSENT'}
        $result.pilot_sacl_ace_count = $acl.Audit.Count
    } catch { $result.pilot_sacl = 'UNKNOWN_READ_FAILED' }
}
$existing = Get-Service -Name SosnadminStorageCollector -ErrorAction SilentlyContinue
$new = Get-Service -Name SosnadminStorageAudit -ErrorAction SilentlyContinue
$result.usn_service = if ($existing) {[string]$existing.Status} else {'NOT_FOUND'}
$result.audit_service = if ($new) {[string]$new.Status} else {'NOT_INSTALLED'}
$result.mutations = 'NONE'
$result | ConvertTo-Json -Depth 5 -Compress
