# Atualizador do Robo Bravus - baixa a versao mais nova do GitHub e instala sozinho
$ErrorActionPreference = 'Stop'
try {
  [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
  Write-Host ''
  Write-Host '  ROBO BRAVUS - atualizando...' -ForegroundColor Cyan

  # 1) descobre onde o robo esta instalado (pelo atalho da Area de Trabalho)
  $desk = [Environment]::GetFolderPath('Desktop')
  $sh = New-Object -ComObject WScript.Shell
  $dir = $null; $pyw = $null
  foreach ($n in 'Ligar Robo Bravus.lnk', 'Robo Bravus.lnk') {
    $p = Join-Path $desk $n
    if (Test-Path $p) {
      $l = $sh.CreateShortcut($p)
      if ($l.WorkingDirectory) { $dir = $l.WorkingDirectory; $pyw = $l.TargetPath; break }
    }
  }
  if (-not $dir) { $dir = Join-Path ([Environment]::GetFolderPath('MyDocuments')) 'RoboBravus' }
  Write-Host "  Pasta: $dir"

  # 2) acha o Python
  $py = $null
  if ($pyw -and (Test-Path $pyw)) {
    $cand = Join-Path (Split-Path $pyw) 'python.exe'
    if (Test-Path $cand) { $py = $cand }
  }
  if (-not $py) {
    $c = Get-Command py -ErrorAction SilentlyContinue
    if ($c) { $py = (& py -3 -c "import sys;print(sys.executable)").Trim() }
  }
  if (-not $py) { throw 'Python nao encontrado. Rode o INSTALAR.bat uma vez.' }

  # 3) fecha o robo se estiver aberto
  Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*robo_bravus.pyw*' } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
  Start-Sleep -Seconds 1

  # 4) baixa e copia os arquivos novos (mantem suas configuracoes)
  $zip = Join-Path $env:TEMP 'robo-bravus.zip'
  $ex = Join-Path $env:TEMP 'robo-bravus-ex'
  Write-Host '  Baixando a versao nova...'
  Invoke-WebRequest -UseBasicParsing 'https://github.com/bravusmidia/robo-bravus/archive/refs/heads/main.zip' -OutFile $zip
  if (Test-Path $ex) { Remove-Item $ex -Recurse -Force }
  Expand-Archive $zip $ex -Force
  $src = Join-Path $ex 'robo-bravus-main'
  New-Item -ItemType Directory -Force $dir | Out-Null
  Get-ChildItem $src -Force | Where-Object { $_.Name -notin 'config.json', '.gitattributes', 'README.md' } |
    Copy-Item -Destination $dir -Recurse -Force

  # 5) componentes, atalhos e abre o robo
  Write-Host '  Instalando componentes...'
  & $py -m pip install -q --disable-pip-version-check -r (Join-Path $dir 'requirements.txt')
  & $py (Join-Path $dir 'robo_bravus.pyw') --instalar
  Write-Host ''
  Write-Host '  PRONTO! Robo Bravus atualizado.' -ForegroundColor Green
  Start-Sleep -Seconds 4
} catch {
  Write-Host ''
  Write-Host ('  ERRO: ' + $_.Exception.Message) -ForegroundColor Red
  Read-Host '  Tire um print desta tela e aperte Enter para fechar'
}
