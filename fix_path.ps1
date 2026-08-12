$pythonPath = "C:\Users\12974\AppData\Local\Programs\Python\Python313"
$scriptsPath = "C:\Users\12974\AppData\Local\Programs\Python\Python313\Scripts"

$currentPath = [Environment]::GetEnvironmentVariable("Path", "User")

# 检查是否已加入
if ($currentPath -notlike "*$pythonPath*") {
    $newPath = "$pythonPath;$scriptsPath;$currentPath"
    [Environment]::SetEnvironmentVariable("Path", $newPath, "User")
    Write-Host "Python paths added to User PATH successfully"
} else {
    Write-Host "Python paths already in User PATH"
}

# 验证
Write-Host "`nCurrent User PATH:"
[Environment]::GetEnvironmentVariable("Path", "User") -split ";" | Where-Object { $_ -like "*Python*" }
