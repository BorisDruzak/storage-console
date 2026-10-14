# Fixed packaged read-only protocol. Input is data, never executable PowerShell.
$ErrorActionPreference = 'Stop'
[Console]::InputEncoding = [Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$directoryConnection = $null

function Emit-DirectoryFrame($frame) {
    [Console]::Out.WriteLine(($frame | ConvertTo-Json -Compress -Depth 8))
    [Console]::Out.Flush()
}
function Directory-Text($entry, $attribute) {
    if ($entry.Attributes.Contains($attribute) -and $entry.Attributes[$attribute].Count -eq 1) {
        return [string]$entry.Attributes[$attribute][0]
    }
    return $null
}
function Directory-ExpectedBase([string]$domain) {
    return (($domain.Split([char]'.') | ForEach-Object { 'DC=' + $_ }) -join ',')
}
function Directory-UInt32($entry, $attribute) {
    $text = Directory-Text $entry $attribute
    $number = [uint32]0
    if ($null -eq $text -or $text -notmatch '^[0-9]{1,10}$' -or
        -not [uint32]::TryParse($text, [ref]$number)) {
        throw 'DIRECTORY_PROTOCOL_INVALID'
    }
    return $number
}
function Directory-Sid($entry) {
    return ([Security.Principal.SecurityIdentifier]::new(
        [byte[]]$entry.Attributes['objectSid'][0], 0)).Value
}
function Directory-Guid($entry) {
    return ([Guid]::new([byte[]]$entry.Attributes['objectGUID'][0])).ToString('D')
}
function Directory-Connect($inputConfig) {
    Add-Type -AssemblyName System.DirectoryServices.Protocols
    $identifier = [DirectoryServices.Protocols.LdapDirectoryIdentifier]::new(
        [string]$inputConfig.ldap_server, 389, $true, $false)
    $connection = [DirectoryServices.Protocols.LdapConnection]::new($identifier)
    $connection.AuthType = [DirectoryServices.Protocols.AuthType]::Kerberos
    $connection.Timeout = [TimeSpan]::FromSeconds(3)
    $connection.SessionOptions.ProtocolVersion = 3
    $connection.SessionOptions.Signing = $true
    $connection.SessionOptions.Sealing = $true
    $connection.SessionOptions.ReferralChasing = [DirectoryServices.Protocols.ReferralChasingOptions]::None
    try {
        $connection.Bind()
        $request = [DirectoryServices.Protocols.SearchRequest]::new(
            '', '(objectClass=*)', [DirectoryServices.Protocols.SearchScope]::Base,
            [string[]]@('defaultNamingContext'))
        $response = [DirectoryServices.Protocols.SearchResponse]$connection.SendRequest($request)
        if ($response.Entries.Count -ne 1) { throw 'DIRECTORY_SCOPE_MISMATCH' }
        $actualBase = Directory-Text $response.Entries[0] 'defaultNamingContext'
        $expectedBase = Directory-ExpectedBase $inputConfig.scope.dns_domain
        if (-not [string]::Equals($actualBase, $expectedBase, [StringComparison]::OrdinalIgnoreCase)) {
            throw 'DIRECTORY_SCOPE_MISMATCH'
        }
        $request = [DirectoryServices.Protocols.SearchRequest]::new(
            $actualBase, '(objectClass=domainDNS)', [DirectoryServices.Protocols.SearchScope]::Base,
            [string[]]@('objectSid'))
        $response = [DirectoryServices.Protocols.SearchResponse]$connection.SendRequest($request)
        if ($response.Entries.Count -ne 1 -or
            (Directory-Sid $response.Entries[0]) -ne $inputConfig.scope.domain_sid) {
            throw 'DIRECTORY_SCOPE_MISMATCH'
        }
        return @{ connection = $connection; base = $actualBase }
    } catch {
        $connection.Dispose()
        throw
    }
}

try {
    $configLine = [Console]::In.ReadLine()
    if ($null -eq $configLine -or $configLine.Length -gt 8192) { throw 'DIRECTORY_LIMIT' }
    $inputConfig = $configLine | ConvertFrom-Json
    if ([Security.Principal.WindowsIdentity]::GetCurrent().User.Value -ne 'S-1-5-18') {
        throw 'MACHINE_IDENTITY_REQUIRED'
    }
    if ($inputConfig.mode -eq 'users') {
        $session = Directory-Connect $inputConfig
        $directoryConnection = $session.connection
        $pageCookie = [byte[]]@()
        $pageIndex = 0
        $recordCount = 0
        $seenCookies = [Collections.Generic.HashSet[string]]::new()
        do {
            if ($pageIndex -ge 512) { throw 'DIRECTORY_LIMIT' }
            $request = [DirectoryServices.Protocols.SearchRequest]::new(
                $session.base, '(&(objectCategory=person)(objectClass=user))',
                [DirectoryServices.Protocols.SearchScope]::Subtree,
                [string[]]@('objectSid','objectGUID','sAMAccountName','userPrincipalName',
                            'displayName','userAccountControl','primaryGroupID'))
            $control = [DirectoryServices.Protocols.PageResultRequestControl]::new([int]$inputConfig.page_size)
            $control.IsCritical = $true
            $control.Cookie = $pageCookie
            [void]$request.Controls.Add($control)
            $response = [DirectoryServices.Protocols.SearchResponse]$directoryConnection.SendRequest($request)
            $pageControls = @($response.Controls | Where-Object {
                $_ -is [DirectoryServices.Protocols.PageResultResponseControl]
            })
            if ($pageControls.Count -ne 1) { throw 'DIRECTORY_LIMIT' }
            $pageCookie = $pageControls[0].Cookie
            if ($pageCookie.Length -gt 65536) { throw 'DIRECTORY_LIMIT' }
            if ($pageCookie.Length -gt 0 -and
                -not $seenCookies.Add([Convert]::ToBase64String($pageCookie))) { throw 'DIRECTORY_LIMIT' }
            $pageRecords = @($response.Entries | ForEach-Object {
                $entry = $_
                $sid = Directory-Sid $entry
                if (-not $sid.StartsWith($inputConfig.scope.domain_sid + '-', [StringComparison]::Ordinal)) {
                    throw 'DIRECTORY_SCOPE_MISMATCH'
                }
                $flags = Directory-UInt32 $entry 'userAccountControl'
                @{
                    sid = $sid; object_guid = (Directory-Guid $entry)
                    account = (Directory-Text $entry 'sAMAccountName')
                    upn = (Directory-Text $entry 'userPrincipalName')
                    display_name = (Directory-Text $entry 'displayName')
                    enabled = (($flags -band 2) -eq 0)
                    primary_group_id = (Directory-UInt32 $entry 'primaryGroupID')
                }
            })
            $recordCount += $pageRecords.Count
            if ($recordCount -gt $inputConfig.max_objects) { throw 'DIRECTORY_LIMIT' }
            $finished = ($pageCookie.Length -eq 0)
            Emit-DirectoryFrame @{ type='page'; page_index=$pageIndex; records=@($pageRecords); finished=$finished }
            if (-not $finished -and [Console]::In.ReadLine() -ne 'ACK') { throw 'DIRECTORY_STOPPED' }
            $pageIndex++
        } while (-not $finished)
    } elseif ($inputConfig.mode -eq 'lookup') {
        $ptrRows = @()
        $forwardRows = @()
        $computerRows = @()
        try {
            $answers = @(Resolve-DnsName -Name $inputConfig.ip -Type PTR -DnsOnly -NoHostsFile -QuickTimeout)
            $ptrRows = @($answers | Where-Object { $_.Type -eq 'PTR' } | ForEach-Object {
                @{ value=$_.NameHost.TrimEnd('.'); ttl=[int]$_.TTL }
            })
        } catch {
            if ($_.FullyQualifiedErrorId -notlike 'DNS_ERROR_RCODE_NAME_ERROR*') { throw 'DNS_UNAVAILABLE' }
        }
        if ($ptrRows.Count -gt 2) { throw 'LOOKUP_LIMIT' }
        $names = @($ptrRows | ForEach-Object { $_.value.ToLowerInvariant() } | Select-Object -Unique)
        if ($names.Count -eq 1 -and $names[0].EndsWith('.'+$inputConfig.scope.dns_domain,
                                                     [StringComparison]::OrdinalIgnoreCase)) {
            $hostName = $names[0]
            if ($hostName -notmatch '^[a-z0-9.-]{3,253}$') { throw 'LOOKUP_LIMIT' }
            try {
                $answers = @(Resolve-DnsName -Name $hostName -Type A_AAAA -DnsOnly -NoHostsFile -QuickTimeout)
                $forwardRows = @($answers | Where-Object { $_.Type -in @('A','AAAA') } | ForEach-Object {
                    @{ value=$_.IPAddress; ttl=[int]$_.TTL }
                })
            } catch { throw 'DNS_UNAVAILABLE' }
            if ($forwardRows.Count -gt 16) { throw 'LOOKUP_LIMIT' }
            if ($forwardRows.value -contains $inputConfig.ip) {
                $session = Directory-Connect $inputConfig
                $directoryConnection = $session.connection
                $request = [DirectoryServices.Protocols.SearchRequest]::new(
                    $session.base, ('(&(objectCategory=computer)(dNSHostName='+$hostName+'))'),
                    [DirectoryServices.Protocols.SearchScope]::Subtree,
                    [string[]]@('objectSid','objectGUID','name','dNSHostName','userAccountControl'))
                $request.SizeLimit = 2
                try {
                    $response = [DirectoryServices.Protocols.SearchResponse]$directoryConnection.SendRequest($request)
                } catch [DirectoryServices.Protocols.DirectoryOperationException] {
                    if ($_.Exception.Response.ResultCode -eq [DirectoryServices.Protocols.ResultCode]::SizeLimitExceeded) {
                        throw 'MULTIPLE_MATCHES'
                    }
                    throw
                }
                $computerRows = @($response.Entries | ForEach-Object {
                    $entry = $_
                    @{
                        sid=(Directory-Sid $entry); guid=(Directory-Guid $entry)
                        name=(Directory-Text $entry 'name')
                        dns_hostname=(Directory-Text $entry 'dNSHostName')
                        enabled=(((Directory-UInt32 $entry 'userAccountControl') -band 2) -eq 0)
                    }
                })
            }
        }
        Emit-DirectoryFrame @{ type='lookup'; ptr=@($ptrRows); forward=@($forwardRows); computers=@($computerRows) }
    } else { throw 'DIRECTORY_LIMIT' }
} catch {
    $code = [string]$_.Exception.Message
    if ($code -notin @('MACHINE_IDENTITY_REQUIRED','DIRECTORY_SCOPE_MISMATCH','DIRECTORY_LIMIT',
                       'DIRECTORY_STOPPED','DNS_UNAVAILABLE','LOOKUP_LIMIT','MULTIPLE_MATCHES')) { $code='LDAP_UNAVAILABLE' }
    Emit-DirectoryFrame @{ type='error'; code=$code }
    exit 1
} finally {
    if ($null -ne $directoryConnection) { $directoryConnection.Dispose() }
}
