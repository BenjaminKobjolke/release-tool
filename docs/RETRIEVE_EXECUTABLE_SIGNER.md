# Retrieve Executable Signer

## PowerShell Command

To get the signer name from a signed executable:

```powershell
(Get-AuthenticodeSignature 'C:\path\to\file.exe').SignerCertificate.Subject
```

Example output:
```
CN=Your Company Name, O=Your Company Name, L=City, S=State, C=DE
```

The `CN=` (Common Name) field contains the signer name used for the `expected_signer` configuration.

## Get Just the Common Name

```powershell
$sig = Get-AuthenticodeSignature 'C:\path\to\file.exe'
$sig.SignerCertificate.Subject -match 'CN=([^,]+)' | Out-Null
$matches[1]
```

## Check Signature Status

```powershell
(Get-AuthenticodeSignature 'C:\path\to\file.exe').Status
```

Possible values:
- `Valid` - File is signed and signature is valid
- `NotSigned` - File is not signed
- `HashMismatch` - File was modified after signing
- `NotTrusted` - Certificate is not trusted

## Full Signature Details

```powershell
Get-AuthenticodeSignature 'C:\path\to\file.exe' | Format-List *
```
