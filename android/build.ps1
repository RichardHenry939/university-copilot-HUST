# (v1.00.60) Build APK app + widget UC KHÔNG cần Gradle: aapt2 -> javac -> d8 -> zipalign -> apksigner.
# Cần: D:\Android\Sdk (platforms;android-35, build-tools;35.0.0), JDK 17 ở D:\Android\jdk17.
#   powershell -ExecutionPolicy Bypass -File build.ps1            -> build\uc.apk
#   powershell -ExecutionPolicy Bypass -File build.ps1 -Install   -> build + adb install -r lên điện thoại đang cắm
# Khoá ký: khoá debug riêng ở D:\Android\uc-debug.keystore (tự tạo lần đầu, mật khẩu chuẩn debug "android" — chỉ để cài tay, không lên store).
# Đi tắt: không có Gradle nên không có thư viện ngoài (AndroidX); app chỉ dùng API Android gốc + WebView. Cần thư viện thì chuyển sang Gradle.
param([switch]$Install)
$ErrorActionPreference = 'Stop'
$sdk = 'D:\Android\Sdk'; $bt = "$sdk\build-tools\35.0.0"; $jar = "$sdk\platforms\android-35\android.jar"
$env:JAVA_HOME = 'D:\Android\jdk17'; $env:Path = "$env:JAVA_HOME\bin;$env:Path"
$here = $PSScriptRoot; $out = Join-Path $here 'build'
Remove-Item $out -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force "$out\gen", "$out\classes", "$out\dex" | Out-Null

& "$bt\aapt2.exe" compile --dir "$here\res" -o "$out\res.zip"; if ($LASTEXITCODE) { throw 'aapt2 compile loi' }
& "$bt\aapt2.exe" link -I $jar --manifest "$here\AndroidManifest.xml" -A "$here\assets" -o "$out\base.apk" --java "$out\gen" "$out\res.zip" --auto-add-overlay
if ($LASTEXITCODE) { throw 'aapt2 link loi' }

$src = @(Get-ChildItem "$here\src", "$out\gen" -Recurse -Filter *.java | ForEach-Object FullName)
& javac --release 11 -encoding UTF-8 -nowarn -cp $jar -d "$out\classes" @src; if ($LASTEXITCODE) { throw 'javac loi' }
$cls = @(Get-ChildItem "$out\classes" -Recurse -Filter *.class | ForEach-Object FullName)
& "$bt\d8.bat" --min-api 26 --lib $jar --output "$out\dex" @cls; if ($LASTEXITCODE) { throw 'd8 loi' }

Copy-Item "$out\base.apk" "$out\unsigned.apk"
Push-Location "$out\dex"; & jar uf "$out\unsigned.apk" classes.dex; Pop-Location
& "$bt\zipalign.exe" -f -p 4 "$out\unsigned.apk" "$out\aligned.apk"; if ($LASTEXITCODE) { throw 'zipalign loi' }

$ks = 'D:\Android\uc-debug.keystore'
if (-not (Test-Path $ks)) { & keytool -genkeypair -keystore $ks -storepass android -keypass android -alias uc -keyalg RSA -keysize 2048 -validity 10000 -dname 'CN=UC debug' | Out-Null }
& "$bt\apksigner.bat" sign --ks $ks --ks-pass pass:android --ks-key-alias uc --out "$out\uc.apk" "$out\aligned.apk"; if ($LASTEXITCODE) { throw 'apksigner loi' }
Write-Host ("Da build: $out\uc.apk ({0:N0} KB)" -f ((Get-Item "$out\uc.apk").Length / 1KB))

if ($Install) {
    $adb = "$sdk\platform-tools\adb.exe"
    $dev = (& $adb devices) -split "`n" | Where-Object { $_ -match "`tdevice" -and $_ -notmatch '^emulator-' } | Select-Object -First 1
    if (-not $dev) { throw 'Khong thay dien thoai (adb). Cam day + bat USB debugging.' }
    & $adb -s ($dev -split "`t")[0] install -r "$out\uc.apk"
}
