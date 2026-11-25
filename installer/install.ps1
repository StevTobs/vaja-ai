# VAJA AI one-click installer (Windows 10/11, no admin rights, no terminal needed).
# Started by "Install VAJA AI.cmd". Installs everything inside this folder plus a private
# Python 3.11 (only if the machine has none), then creates desktop / Start Menu shortcuts.
# -Auto runs without the window (for testing); -SkipModel / -NoShortcut skip those steps.
param([switch]$Auto, [switch]$SkipModel, [switch]$NoShortcut)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$Root = Split-Path -Parent $PSScriptRoot
$LogDir = Join-Path $Root 'data\logs'
New-Item -ItemType Directory -Force $LogDir | Out-Null
$InstallLog = Join-Path $LogDir 'install.log'
$PythonUrl = 'https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe'
$FfmpegUrl = 'https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip'
$PrivatePython = Join-Path $env:LOCALAPPDATA 'Programs\VAJA-AI\Python311'
$Venv = Join-Path $Root '.venv'
$VenvPython = Join-Path $Venv 'Scripts\python.exe'
$VenvPythonW = Join-Path $Venv 'Scripts\pythonw.exe'
$Ui = $null
# Windows' own tools; a tar/curl from Git or MSYS earlier in PATH parses C:\ paths as remote hosts.
$Curl = Join-Path $env:SystemRoot 'System32\curl.exe'
$Tar = Join-Path $env:SystemRoot 'System32\tar.exe'

# Logging must never stop the install (antivirus or an open viewer can lock the file briefly).
function Add-LogText([string]$text) {
    for ($i = 0; $i -lt 5; $i++) {
        try {
            $fs = [System.IO.File]::Open($InstallLog, 'Append', 'Write', 'ReadWrite')
            try { $bytes = [System.Text.Encoding]::UTF8.GetBytes($text + "`r`n"); $fs.Write($bytes, 0, $bytes.Length) }
            finally { $fs.Close() }
            return
        } catch { Start-Sleep -Milliseconds 200 }
    }
}

function Write-Log([string]$text) {
    Add-LogText ("[{0}] {1}" -f (Get-Date -Format 'HH:mm:ss'), $text)
    if ($Ui) { $Ui.Log.AppendText($text + "`r`n"); [System.Windows.Forms.Application]::DoEvents() }
    else { Write-Host $text }
}

function Set-Status([string]$text) {
    if ($Ui) { $Ui.Status.Text = $text; [System.Windows.Forms.Application]::DoEvents() }
}

function Read-Tail([string]$path) {
    try {
        $fs = [System.IO.File]::Open($path, 'Open', 'Read', 'ReadWrite')
        try {
            $len = [Math]::Min($fs.Length, 4000)
            if ($len -le 0) { return '' }
            $fs.Seek(-$len, 'End') | Out-Null
            $buf = New-Object byte[] $len
            [void]$fs.Read($buf, 0, $len)
            $text = [System.Text.Encoding]::UTF8.GetString($buf)
            $parts = $text -split "[`r`n]+" | Where-Object { $_.Trim() }
            if ($parts) { return ($parts[-1]).Trim() } else { return '' }
        } finally { $fs.Close() }
    } catch { return '' }
}

# Run a program hidden, keep the window responsive and show its latest output line.
function Invoke-Hidden([string]$file, [string]$arguments, [string]$label) {
    $out = Join-Path $LogDir 'step.out.log'
    $err = Join-Path $LogDir 'step.err.log'
    Remove-Item $out, $err -ErrorAction SilentlyContinue
    $p = Start-Process -FilePath $file -ArgumentList $arguments -WorkingDirectory $Root -WindowStyle Hidden `
        -PassThru -RedirectStandardOutput $out -RedirectStandardError $err
    $null = $p.Handle  # keeps ExitCode available after exit
    while (-not $p.HasExited) {
        $line = Read-Tail $err
        if (-not $line) { $line = Read-Tail $out }
        if ($line) {
            if ($line.Length -gt 110) { $line = $line.Substring(0, 110) + '…' }
            Set-Status "$label · $line"
        }
        if ($Ui) { [System.Windows.Forms.Application]::DoEvents() }
        Start-Sleep -Milliseconds 200
    }
    $p.WaitForExit()
    foreach ($f in @($out, $err)) {
        if (Test-Path $f) { try { Add-LogText ([System.IO.File]::ReadAllText($f)) } catch { } }
    }
    if ($p.ExitCode -ne 0) {
        $detail = Read-Tail $err
        throw "$label ไม่สำเร็จ (รหัส $($p.ExitCode)) $detail"
    }
}

function Get-File([string]$url, [string]$dest, [string]$label) {
    Invoke-Hidden $Curl "-L --fail --retry 3 --retry-delay 2 -o `"$dest`" `"$url`"" $label
}

function Test-Python311([string]$exe) {
    if (-not $exe -or -not (Test-Path $exe)) { return $false }
    try {
        $v = & $exe -c "import sys;print('%d.%d' % sys.version_info[:2])" 2>$null
        return ($v -eq '3.11')
    } catch { return $false }
}

function Find-Python {
    $candidates = @(
        (Join-Path $PrivatePython 'python.exe'),
        (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python311\python.exe'),
        'C:\Program Files\Python311\python.exe'
    )
    try {
        $fromLauncher = & py -3.11 -c "import sys;print(sys.executable)" 2>$null
        if ($fromLauncher) { $candidates = @($fromLauncher.Trim()) + $candidates }
    } catch { }
    foreach ($c in $candidates) { if (Test-Python311 $c) { return $c } }
    return $null
}

function Test-NvidiaGpu {
    try { $null = & nvidia-smi -L 2>$null; return ($LASTEXITCODE -eq 0) } catch { return $false }
}

function New-Shortcut([string]$path, [string]$arguments, [string]$description) {
    # WScript.Shell saves through an ANSI path, so a Thai file name becomes "???" and fails.
    # Save under an ASCII temp name in the same folder, then rename (PowerShell handles Unicode).
    $folder = Split-Path -Parent $path
    $temp = Join-Path $folder ("vaja-" + [guid]::NewGuid().ToString('N') + '.lnk')
    $shell = New-Object -ComObject WScript.Shell
    $lnk = $shell.CreateShortcut($temp)
    $lnk.TargetPath = $VenvPythonW
    $lnk.Arguments = $arguments
    $lnk.WorkingDirectory = $Root
    $lnk.Description = $description
    $icon = Join-Path $Root 'app\static\vaja.ico'
    if (Test-Path -LiteralPath $icon) { $lnk.IconLocation = "$icon,0" }
    else { $lnk.IconLocation = "$env:SystemRoot\System32\SndVol.exe,0" }
    $lnk.Save()
    if (Test-Path -LiteralPath $path) { Remove-Item -LiteralPath $path -Force }
    Move-Item -LiteralPath $temp -Destination $path -Force
}

function Install-All([bool]$useGpu, [bool]$downloadModel, [bool]$desktopShortcut) {
    $steps = 7
    $script:n = 0
    function Step([string]$text) {
        $script:n++
        Write-Log "($script:n/$steps) $text"
        Set-Status $text
        if ($Ui) { $Ui.Progress.Value = [Math]::Min($Ui.Progress.Maximum, $script:n - 1) }
    }
    Set-Location $Root
    Write-Log "ติดตั้งที่ $Root"
    # Files extracted from a downloaded zip are marked as from the internet; unmark ours.
    Get-ChildItem -Path $Root -Recurse -File -ErrorAction SilentlyContinue |
        Where-Object { $_.FullName -notlike "$Venv*" } | Unblock-File -ErrorAction SilentlyContinue

    Step 'ตรวจสอบ Python 3.11'
    if (Test-Python311 $VenvPython) {
        Write-Log 'มี virtual environment แล้ว'
    } else {
        $python = Find-Python
        if (-not $python) {
            Write-Log 'ไม่พบ Python 3.11 · ดาวน์โหลดและติดตั้งเฉพาะผู้ใช้นี้'
            $setup = Join-Path $env:TEMP 'vaja-python-3.11.9-amd64.exe'
            Get-File $PythonUrl $setup 'ดาวน์โหลด Python'
            Invoke-Hidden $setup "/quiet InstallAllUsers=0 PrependPath=0 Include_launcher=0 Include_test=0 Shortcuts=0 AssociateFiles=0 TargetDir=`"$PrivatePython`"" 'ติดตั้ง Python'
            Remove-Item $setup -ErrorAction SilentlyContinue
            $python = Join-Path $PrivatePython 'python.exe'
            if (-not (Test-Python311 $python)) { throw 'ติดตั้ง Python ไม่สำเร็จ' }
        }
        Write-Log "ใช้ Python: $python"
        if (Test-Path $Venv) { Remove-Item -Recurse -Force $Venv }
        Invoke-Hidden $python "-m venv `"$Venv`"" 'สร้าง virtual environment'
    }
    Step 'ตรวจสอบ FFmpeg'
    $bundled = Join-Path $Root 'tools\ffmpeg\bin\ffmpeg.exe'
    $hasSystem = (Get-Command ffmpeg -ErrorAction SilentlyContinue) -and (Get-Command ffprobe -ErrorAction SilentlyContinue)
    if ((Test-Path $bundled) -or $hasSystem) {
        Write-Log 'มี FFmpeg แล้ว'
    } else {
        $tools = Join-Path $Root 'tools'
        New-Item -ItemType Directory -Force $tools | Out-Null
        $zip = Join-Path $tools 'ffmpeg.zip'
        Get-File $FfmpegUrl $zip 'ดาวน์โหลด FFmpeg'
        $extract = Join-Path $tools 'ffmpeg-extract'
        if (Test-Path $extract) { Remove-Item -Recurse -Force $extract }
        New-Item -ItemType Directory -Force $extract | Out-Null
        Invoke-Hidden $Tar "-xf `"$zip`" -C `"$extract`"" 'แตกไฟล์ FFmpeg'
        $bin = Get-ChildItem -Path $extract -Recurse -Filter 'ffprobe.exe' | Select-Object -First 1
        if (-not $bin) { throw 'ไม่พบ ffprobe.exe ในไฟล์ที่ดาวน์โหลด' }
        $target = Join-Path $tools 'ffmpeg\bin'
        New-Item -ItemType Directory -Force $target | Out-Null
        Copy-Item (Join-Path $bin.DirectoryName '*.exe') $target -Force
        Remove-Item -Recurse -Force $extract, $zip
        Write-Log "ติดตั้ง FFmpeg ที่ $target"
    }

    Step 'ติดตั้งไลบรารีของโปรแกรม (อาจใช้เวลาหลายนาที)'
    Invoke-Hidden $VenvPython "-m pip install --disable-pip-version-check --no-input -r `"$Root\requirements.lock.txt`"" 'ติดตั้งไลบรารี'
    if ($useGpu) {
        Invoke-Hidden $VenvPython "-m pip install --disable-pip-version-check --no-input -r `"$Root\requirements-gpu-windows.txt`"" 'ติดตั้ง NVIDIA runtime'
    }

    Step 'ตั้งค่าเริ่มต้น'
    $envFile = Join-Path $Root '.env'
    if (Test-Path $envFile) {
        Write-Log 'มีไฟล์ .env แล้ว ใช้ค่าเดิม'
    } else {
        $template = 'env.example'
        if ($useGpu) { $template = 'env.gpu.example' }
        Copy-Item (Join-Path $Root ".$template") $envFile
        Write-Log "สร้าง .env จาก .$template (แก้ค่าต่อได้ในหน้า ตั้งค่า ของโปรแกรม)"
    }

    Step 'ดาวน์โหลดโมเดลถอดเสียง'
    if ($downloadModel) {
        Invoke-Hidden $VenvPython '-m scripts.download_model' 'ดาวน์โหลดโมเดล'
    } else { Write-Log 'ข้าม (ดาวน์โหลดภายหลังได้ในหน้า ตั้งค่า)' }

    Step 'สร้างไอคอนเปิดโปรแกรม'
    if (-not $NoShortcut) {
        $menu = Join-Path ([Environment]::GetFolderPath('Programs')) 'VAJA AI'
        New-Item -ItemType Directory -Force $menu | Out-Null
        New-Shortcut (Join-Path $menu 'VAJA AI.lnk') '-m scripts.launch' 'เปิด VAJA AI'
        New-Shortcut (Join-Path $menu 'ปิด VAJA AI.lnk') '-m scripts.launch --stop' 'ปิด VAJA AI'
        if ($desktopShortcut) {
            New-Shortcut (Join-Path ([Environment]::GetFolderPath('Desktop')) 'VAJA AI.lnk') '-m scripts.launch' 'เปิด VAJA AI'
        }
        Write-Log 'สร้างไอคอน VAJA AI ใน Start Menu แล้ว'
    }

    Step 'ตรวจสอบการติดตั้ง'
    Invoke-Hidden $VenvPython '-c "import fastapi, faster_whisper, anthropic, sherpa_onnx, app.main"' 'ตรวจสอบโปรแกรม'
    if ($Ui) { $Ui.Progress.Value = $Ui.Progress.Maximum }
    Write-Log 'ติดตั้งเสร็จแล้ว'
}

if ($Auto) {
    Install-All (Test-NvidiaGpu) (-not $SkipModel) $true
    exit 0
}

# ---------------------------------------------------------------------------- window
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
[System.Windows.Forms.Application]::EnableVisualStyles()
$font = New-Object System.Drawing.Font('Tahoma', 10)
$form = New-Object System.Windows.Forms.Form
$form.Text = 'ติดตั้ง VAJA AI'
$form.Size = New-Object System.Drawing.Size(780, 600)
$form.StartPosition = 'CenterScreen'
$form.Font = $font
$form.FormBorderStyle = 'FixedDialog'
$form.MaximizeBox = $false

$title = New-Object System.Windows.Forms.Label
$title.Text = 'VAJA AI · ถอดเสียงภาษาไทย'
$title.Font = New-Object System.Drawing.Font('Tahoma', 16, [System.Drawing.FontStyle]::Bold)
$title.ForeColor = [System.Drawing.Color]::FromArgb(104, 44, 145)
$title.SetBounds(24, 18, 720, 34)
$form.Controls.Add($title)

$desc = New-Object System.Windows.Forms.Label
$desc.Text = "กด ติดตั้ง ครั้งเดียว โปรแกรมจะติดตั้ง Python, FFmpeg, ไลบรารี และโมเดลถอดเสียงให้อัตโนมัติ`r`nต้องต่ออินเทอร์เน็ต ใช้พื้นที่ประมาณ 3-10 GB ไม่ต้องใช้สิทธิ์ผู้ดูแลระบบ"
$desc.SetBounds(24, 58, 720, 44)
$form.Controls.Add($desc)

$hasGpu = Test-NvidiaGpu
$gpu = New-Object System.Windows.Forms.CheckBox
$gpu.SetBounds(24, 108, 720, 24)
if ($hasGpu) { $gpu.Text = 'ใช้การ์ดจอ NVIDIA (ตรวจพบ) · ถอดเสียงเร็วกว่าและใช้โมเดลภาษาไทยที่แม่นกว่า'; $gpu.Checked = $true }
else { $gpu.Text = 'ใช้การ์ดจอ NVIDIA (ไม่พบในเครื่องนี้ · ใช้ CPU)'; $gpu.Enabled = $false }
$form.Controls.Add($gpu)

$model = New-Object System.Windows.Forms.CheckBox
$model.Text = 'ดาวน์โหลดโมเดลถอดเสียงตอนติดตั้ง (แนะนำ)'
$model.Checked = $true
$model.SetBounds(24, 134, 720, 24)
$form.Controls.Add($model)

$desktop = New-Object System.Windows.Forms.CheckBox
$desktop.Text = 'สร้างไอคอน VAJA AI บน Desktop'
$desktop.Checked = $true
$desktop.SetBounds(24, 160, 720, 24)
$form.Controls.Add($desktop)

$progress = New-Object System.Windows.Forms.ProgressBar
$progress.SetBounds(24, 196, 716, 22)
$progress.Maximum = 7
$form.Controls.Add($progress)

$status = New-Object System.Windows.Forms.Label
$status.Text = 'พร้อมติดตั้ง'
$status.SetBounds(24, 222, 716, 22)
$status.AutoEllipsis = $true
$form.Controls.Add($status)

$log = New-Object System.Windows.Forms.TextBox
$log.Multiline = $true
$log.ReadOnly = $true
$log.ScrollBars = 'Vertical'
$log.BackColor = [System.Drawing.Color]::White
$log.SetBounds(24, 250, 716, 236)
$form.Controls.Add($log)

$install = New-Object System.Windows.Forms.Button
$install.Text = 'ติดตั้ง'
$install.SetBounds(440, 502, 150, 40)
$install.BackColor = [System.Drawing.Color]::FromArgb(104, 44, 145)
$install.ForeColor = [System.Drawing.Color]::White
$install.FlatStyle = 'Flat'
$form.Controls.Add($install)

$open = New-Object System.Windows.Forms.Button
$open.Text = 'เปิด VAJA AI'
$open.SetBounds(600, 502, 140, 40)
$open.Enabled = $false
$form.Controls.Add($open)

$close = New-Object System.Windows.Forms.Button
$close.Text = 'ปิด'
$close.SetBounds(24, 502, 100, 40)
$form.Controls.Add($close)

$Ui = @{ Log = $log; Status = $status; Progress = $progress }
$script:busy = $false

$install.Add_Click({
    $script:busy = $true
    foreach ($c in @($install, $gpu, $model, $desktop, $close)) { $c.Enabled = $false }
    $progress.Value = 0
    try {
        Install-All ($gpu.Checked -and $hasGpu) $model.Checked $desktop.Checked
        $status.Text = 'ติดตั้งเสร็จแล้ว · กด เปิด VAJA AI หรือดับเบิลคลิกไอคอน VAJA AI บน Desktop'
        $open.Enabled = $true
        $install.Text = 'ติดตั้งซ้ำ'
    } catch {
        Write-Log ("ผิดพลาด: " + $_.Exception.Message)
        $status.Text = 'ติดตั้งไม่สำเร็จ · ตรวจอินเทอร์เน็ตแล้วกด ติดตั้ง อีกครั้ง (รายละเอียดใน data\logs\install.log)'
        $install.Text = 'ลองอีกครั้ง'
    } finally {
        $script:busy = $false
        foreach ($c in @($install, $model, $desktop, $close)) { $c.Enabled = $true }
        $gpu.Enabled = $hasGpu
    }
})
$open.Add_Click({
    Start-Process -FilePath $VenvPythonW -ArgumentList '-m scripts.launch' -WorkingDirectory $Root
    $form.Close()
})
$close.Add_Click({ $form.Close() })
$form.Add_FormClosing({ param($s, $e) if ($script:busy) { $e.Cancel = $true } })
[void]$form.ShowDialog()
