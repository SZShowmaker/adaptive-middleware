$ErrorActionPreference = 'Stop'
python "$PSScriptRoot/amw" @args
exit $LASTEXITCODE
