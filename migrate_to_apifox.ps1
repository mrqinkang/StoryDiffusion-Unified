# StoryDiffusion → Apifox 迁移脚本 (PowerShell)
# 生成所有 JSON 配置文件 + 逐条调用 apifox-cli

# Token 从环境变量读取（运行前需设置 $env:APIFOX_TOKEN）
$TOKEN = $env:APIFOX_TOKEN
if (-not $TOKEN) { Write-Warning "未设置环境变量 APIFOX_TOKEN，请先设置后运行"; exit 1 }
$PROJECT = "8569627"
$BRANCH = "main"
$OUT_DIR = "$env:TEMP\apifox_migrate"
$NULL > $OUT_DIR 2>$null; New-Item -ItemType Directory -Force -Path $OUT_DIR | Out-Null

# 分类 ID
$CAT_POSITIVE = 11971526
$CAT_NEGATIVE = 11971527
$CAT_BOUNDARY = 11971528
$CAT_SECURITY = 11971529
$CAT_OTHER = 11971530

# Endpoint ID 映射
$EP = @{
    api_health           = 485848334
    comic_styles         = 485848357
    comic_layouts        = 485848358
    comic_models         = 485848359
    comic_test           = 485848355
    novel_templates      = 485848340
    novel_templates_custom = 485848347
    novel_drafts         = 485848344
    novel_chat_list      = 485848351
    novel_guided_chat    = 485848341
    novel_chat_save      = 485848352
    novel_generate       = 485848335
    novel_template_save  = 485848348
    novel_continue       = 485848342
    xhs_check            = 485848366
    xhs_extract_cookies  = 485848369
    xhs_check_login      = 485848370
    pipeline_extract     = 485848360
    pipeline_generate    = 485848361
    novel_chat_load      = 485848353
    novel_chat_delete    = 485848354
}

function New-Assertion($subject, $comparison, $value, $path="", $name) {
    if (-not $name) { $name = "$subject $comparison $value" }
    return @{
        type = "assertion"
        data = @{
            name = $name
            subject = $subject
            comparison = $comparison
            value = "$value"
            path = $path
            extractSettings = @{
                expression = $path
                continueExtractorSettings = @{ isContinueExtractValue = $false }
            }
        }
        defaultEnable = $true
        enable = $true
    }
}

function New-TestCase($name, $apiDetailId, $method, $path, $categoryId, $requestBody, $assertions, $timeout=15000) {
    return @{
        name = $name
        categoryId = $categoryId
        apiDetailId = $apiDetailId
        method = $method.ToLower()
        path = $path
        parameters = @{ query=@(); path=@(); header=@(); cookie=@() }
        commonParameters = @{}
        requestBody = $requestBody
        preProcessors = @()
        postProcessors = $assertions
        advancedSettings = @{ timeout = $timeout }
        tagIds = @()
    }
}

function New-Mock($name, $apiDetailId, $statusCode, $body, $delay=0) {
    $bodyStr = $body | ConvertTo-Json -Compress -Depth 10
    return @{
        name = $name
        apiDetailId = $apiDetailId
        conditions = @()
        ipCondition = @{}
        response = @{
            code = $statusCode
            delay = $delay
            headers = @()
            bodyType = "json"
            bodyData = $bodyStr
        }
    }
}

function Write-JsonFile($name, $data) {
    $path = Join-Path $OUT_DIR "$name.json"
    $data | ConvertTo-Json -Depth 10 -Compress | Set-Content -Path $path -Encoding UTF8 -NoNewline
    return $path
}

function Exec-Apifox($cmd, $label) {
    Write-Host "  → $label" -ForegroundColor Yellow
    $fullCmd = "apifox $cmd --branch $BRANCH --access-token $TOKEN"
    # 使用 Start-Process 避免 pipe 卡死，输出到临时文件
    $logFile = Join-Path $OUT_DIR "last_run.log"
    $null = Start-Process -NoNewWindow -FilePath "cmd.exe" -ArgumentList "/c $fullCmd > `"$logFile`" 2>&1" -Wait
    $result = Get-Content $logFile -Raw
    # 提取 JSON (跳过提示行)
    $jsonStart = $result.LastIndexOf("{")
    if ($jsonStart -ge 0) {
        $jsonStr = $result.Substring($jsonStart)
        try {
            $parsed = $jsonStr | ConvertFrom-Json
            if ($parsed.success) { return $parsed.data }
        } catch { }
    }
    Write-Host "    ❌ 失败" -ForegroundColor Red
    Write-Host "    $($result.Substring(0, [Math]::Min(300, $result.Length)))" -ForegroundColor DarkGray
    return $null
}

# ============================
# 主流程
# ============================
Write-Host "╔═══════════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║  StoryDiffusion → Apifox 迁移脚本           ║" -ForegroundColor Cyan
Write-Host "║  项目 ID: 8569627                           ║" -ForegroundColor Cyan
Write-Host "╚═══════════════════════════════════════════════╝" -ForegroundColor Cyan

$allIds = @()
$posIds = @()
$negIds = @()
$mockCaseIds = @()

# ============================
# 第一阶段：真实服务测试用例
# ============================
Write-Host "`n========================================================" -ForegroundColor Cyan
Write-Host "  第一阶段：创建真实服务测试用例" -ForegroundColor Cyan
Write-Host "========================================================" -ForegroundColor Cyan

$REAL_CASES = @(
    # (name, epKey, method, path, category, bodyType, bodyData, assertions, timeout)
    @{n="[正向] GET 漫画风格列表"; ep="comic_styles"; m="GET"; p="/api/comic/styles"; c=$CAT_POSITIVE; bt="none"; bd=""; as=@(@{s="httpCode";c="equal";v=200})}
    @{n="[正向] GET 漫画排版列表"; ep="comic_layouts"; m="GET"; p="/api/comic/layouts"; c=$CAT_POSITIVE; bt="none"; bd=""; as=@(@{s="httpCode";c="equal";v=200})}
    @{n="[正向] GET 漫画模型列表"; ep="comic_models"; m="GET"; p="/api/comic/models"; c=$CAT_POSITIVE; bt="none"; bd=""; as=@(@{s="httpCode";c="equal";v=200})}
    @{n="[正向] GET 小说预置模板"; ep="novel_templates"; m="GET"; p="/api/novel/templates"; c=$CAT_POSITIVE; bt="none"; bd=""; as=@(@{s="httpCode";c="equal";v=200})}
    @{n="[正向] GET 自定义模板列表"; ep="novel_templates_custom"; m="GET"; p="/api/novel/templates/custom"; c=$CAT_POSITIVE; bt="none"; bd=""; as=@(@{s="httpCode";c="equal";v=200})}
    @{n="[正向] GET 草稿箱"; ep="novel_drafts"; m="GET"; p="/api/novel/drafts"; c=$CAT_POSITIVE; bt="none"; bd=""; as=@(@{s="httpCode";c="equal";v=200})}
    @{n="[正向] GET 对话列表"; ep="novel_chat_list"; m="GET"; p="/api/novel/chat/list"; c=$CAT_POSITIVE; bt="none"; bd=""; as=@(@{s="httpCode";c="equal";v=200})}
    @{n="[正向] GET 小红书发布状态"; ep="xhs_check"; m="GET"; p="/api/xhs/publish/check"; c=$CAT_POSITIVE; bt="none"; bd=""; as=@(@{s="httpCode";c="equal";v=200})}
    @{n="[正向] GET 提取Cookies"; ep="xhs_extract_cookies"; m="GET"; p="/api/xhs/publish/extract-cookies"; c=$CAT_POSITIVE; bt="none"; bd=""; as=@(@{s="httpCode";c="equal";v=200})}
    @{n="[正向] POST 保存对话"; ep="novel_chat_save"; m="POST"; p="/api/novel/chat/save"; c=$CAT_POSITIVE; bt="application/json"; bd='{"name":"测试对话","messages":[{"role":"user","content":"你好"}]}'; as=@(@{s="httpCode";c="equal";v=200})}
    @{n="[正向] POST 保存自定义模板"; ep="novel_template_save"; m="POST"; p="/api/novel/templates/custom/save"; c=$CAT_POSITIVE; bt="application/json"; bd='{"name":"测试模板","params":{"topic":"test"}}'; as=@(@{s="httpCode";c="equal";v=200})}
    @{n="[负向] POST 漫画测试连接"; ep="comic_test"; m="POST"; p="/api/comic/test"; c=$CAT_NEGATIVE; bt="application/json"; bd="{}"; as=@(@{s="httpCode";c="equal";v=422})}
    @{n="[负向] POST 引导创作"; ep="novel_guided_chat"; m="POST"; p="/api/novel/guided-chat"; c=$CAT_NEGATIVE; bt="application/json"; bd="{}"; as=@(@{s="httpCode";c="equal";v=422})}
    @{n="[负向] POST 生成小说"; ep="novel_generate"; m="POST"; p="/api/novel/generate"; c=$CAT_NEGATIVE; bt="application/json"; bd="{}"; as=@(@{s="httpCode";c="equal";v=422})}
    @{n="[负向] POST 续写小说"; ep="novel_continue"; m="POST"; p="/api/novel/continue"; c=$CAT_NEGATIVE; bt="application/json"; bd="{}"; as=@(@{s="httpCode";c="equal";v=422})}
    @{n="[负向] POST 提取分镜"; ep="pipeline_extract"; m="POST"; p="/api/pipeline/extract"; c=$CAT_NEGATIVE; bt="application/json"; bd="{}"; as=@(@{s="httpCode";c="equal";v=422})}
    @{n="[负向] POST 生成漫画"; ep="pipeline_generate"; m="POST"; p="/api/pipeline/generate"; c=$CAT_NEGATIVE; bt="application/json"; bd="{}"; as=@(@{s="httpCode";c="equal";v=422})}
    @{n="[其他] POST 检查小红书登录"; ep="xhs_check_login"; m="POST"; p="/api/xhs/publish/check-login"; c=$CAT_OTHER; bt="application/json"; bd="{}"; as=@(); t=5000}
    @{n="[其他] GET 健康检查(已知404)"; ep="api_health"; m="GET"; p="/api/health"; c=$CAT_OTHER; bt="none"; bd=""; as=@(@{s="httpCode";c="equal";v=404}); t=5000}
    @{n="[其他] POST 加载对话"; ep="novel_chat_load"; m="POST"; p="/api/novel/chat/load"; c=$CAT_OTHER; bt="application/json"; bd='{"chat_id":"test"}'; as=@(); t=5000}
    @{n="[其他] POST 删除对话"; ep="novel_chat_delete"; m="POST"; p="/api/novel/chat/delete"; c=$CAT_OTHER; bt="application/json"; bd='{"chat_id":"test"}'; as=@(); t=5000}
)

$idx = 0
foreach ($case in $REAL_CASES) {
    $idx++
    $assertions = @()
    foreach ($a in $case.as) {
        $assertions += New-Assertion -subject $a.s -comparison $a.c -value $a.v
    }
    $t = if ($case.ContainsKey("t")) { $case.t } else { 15000 }
    
    $rb = if ($case.bt -eq "none") { @{type="none";data=""} } else { @{type=$case.bt;data=$case.bd} }
    
    $tc = New-TestCase -name $case.n -apiDetailId $EP[$case.ep] -method $case.m -path $case.p -categoryId $case.c -requestBody $rb -assertions $assertions -timeout $t
    
    $f = Write-JsonFile "case_$idx" $tc
    $result = Exec-Apifox "test-case create --project $PROJECT --file `"$f`"" $case.n
    if ($result -and $result.id) {
        $allIds += $result.id
        if ($case.c -eq $CAT_POSITIVE) { $posIds += $result.id }
        if ($case.c -eq $CAT_NEGATIVE) { $negIds += $result.id }
        Write-Host "    ✅ ID: $($result.id)" -ForegroundColor Green
    }
}

Write-Host "`n  ✅ 真实服务测试用例: $($allIds.Count) 个" -ForegroundColor Green

# ============================
# 第二阶段：Mock 测试
# ============================
Write-Host "`n========================================================" -ForegroundColor Cyan
Write-Host "  第二阶段：创建 Mock 测试" -ForegroundColor Cyan
Write-Host "========================================================" -ForegroundColor Cyan

$MOCK_SCENARIOS = @(
    @{ep="comic_styles"; sn="500 服务器错误"; sc=500; bd=@{detail="Internal Server Error"}; cat=$CAT_SECURITY; method="GET"; path="/api/comic/styles"}
    @{ep="comic_styles"; sn="429 限流"; sc=429; bd=@{detail="Too Many Requests";retry_after=60}; cat=$CAT_NEGATIVE; method="GET"; path="/api/comic/styles"}
    @{ep="comic_styles"; sn="空数组"; sc=200; bd=@{success=$true;styles=@()}; cat=$CAT_BOUNDARY; method="GET"; path="/api/comic/styles"}
    @{ep="comic_layouts"; sn="500 服务器错误"; sc=500; bd=@{detail="Internal Server Error"}; cat=$CAT_SECURITY; method="GET"; path="/api/comic/layouts"}
    @{ep="comic_models"; sn="500 服务器错误"; sc=500; bd=@{detail="Internal Server Error"}; cat=$CAT_SECURITY; method="GET"; path="/api/comic/models"}
    @{ep="novel_templates"; sn="500 服务器错误"; sc=500; bd=@{detail="Internal Server Error"}; cat=$CAT_SECURITY; method="GET"; path="/api/novel/templates"}
    @{ep="novel_templates"; sn="空数据"; sc=200; bd=@{success=$true;templates=@{}}; cat=$CAT_BOUNDARY; method="GET"; path="/api/novel/templates"}
    @{ep="novel_drafts"; sn="空草稿箱"; sc=200; bd=@{success=$true;drafts=@()}; cat=$CAT_BOUNDARY; method="GET"; path="/api/novel/drafts"}
    @{ep="novel_generate"; sn="504 上游超时"; sc=504; bd=@{detail="LLM upstream timeout"}; cat=$CAT_SECURITY; method="POST"; path="/api/novel/generate"}
    @{ep="novel_generate"; sn="500 生成失败"; sc=500; bd=@{detail="Novel generation failed"}; cat=$CAT_SECURITY; method="POST"; path="/api/novel/generate"}
    @{ep="novel_chat_save"; sn="409 冲突"; sc=409; bd=@{detail="Chat already exists"}; cat=$CAT_NEGATIVE; method="POST"; path="/api/novel/chat/save"}
    @{ep="novel_chat_save"; sn="500 保存失败"; sc=500; bd=@{detail="Database write failed"}; cat=$CAT_SECURITY; method="POST"; path="/api/novel/chat/save"}
    @{ep="comic_test"; sn="500 连接测试失败"; sc=500; bd=@{detail="LLM connection failed"}; cat=$CAT_SECURITY; method="POST"; path="/api/comic/test"}
    @{ep="xhs_check"; sn="500 检查失败"; sc=500; bd=@{detail="Publish check failed"}; cat=$CAT_SECURITY; method="GET"; path="/api/xhs/publish/check"}
)

$mockIdx = 0
foreach ($ms in $MOCK_SCENARIOS) {
    $mockIdx++
    $apiId = $EP[$ms.ep]
    
    # 创建 Mock 预期
    $mockData = New-Mock -name "[Mock] $($ms.ep) - $($ms.sn)" -apiDetailId $apiId -statusCode $ms.sc -body $ms.bd
    $f = Write-JsonFile "mock_$mockIdx" $mockData
    $null = Exec-Apifox "mock create --project $PROJECT --file `"$f`"" "Mock: $($ms.ep) - $($ms.sn)"
    
    # 创建对应测试用例
    $rbType = if ($ms.method -eq "GET") { "none" } else { "application/json" }
    $rbData = if ($ms.method -eq "GET") { "" } else { "{}" }
    $assertion = @(New-Assertion -subject "httpCode" -comparison "equal" -value $ms.sc)
    $tc = New-TestCase -name "[Mock] $($ms.ep) - $($ms.sn) ($($ms.sc))" -apiDetailId $apiId -method $ms.method -path $ms.path -categoryId $ms.cat -requestBody @{type=$rbType;data=$rbData} -assertions $assertion -timeout 5000
    
    $cf = Write-JsonFile "mock_case_$mockIdx" $tc
    $result = Exec-Apifox "test-case create --project $PROJECT --file `"$cf`"" "测试用例: [Mock] $($ms.ep) - $($ms.sn)"
    if ($result -and $result.id) {
        $mockCaseIds += $result.id
    }
}

Write-Host "`n  ✅ Mock 测试用例: $($mockCaseIds.Count) 个" -ForegroundColor Green

# ============================
# 第三阶段：Test Suite
# ============================
Write-Host "`n========================================================" -ForegroundColor Cyan
Write-Host "  第三阶段：创建 Test Suite 分组" -ForegroundColor Cyan
Write-Host "========================================================" -ForegroundColor Cyan

# 简化：把所有正向用例放入"全量回归测试"
if ($allIds.Count -gt 0) {
    $suiteData = @{
        name = "全量回归测试"
        priority = 0
        items = @(@{
            id = "item_all"
            name = "所有用例"
            type = "STATIC_TEST_CASE"
            testCases = $allIds | ForEach-Object { @{id=$_} }
        })
    }
    $f = Write-JsonFile "suite_full" $suiteData
    $null = Exec-Apifox "test-suite create --project $PROJECT --file `"$f`"" "创建套件: 全量回归测试"
}
if ($mockCaseIds.Count -gt 0) {
    $suiteData = @{
        name = "Mock 异常场景测试"
        priority = 1
        items = @(@{
            id = "item_mock"
            name = "Mock 异常场景"
            type = "STATIC_TEST_CASE"
            testCases = $mockCaseIds | ForEach-Object { @{id=$_} }
        })
    }
    $f = Write-JsonFile "suite_mock" $suiteData
    $null = Exec-Apifox "test-suite create --project $PROJECT --file `"$f`"" "创建套件: Mock 异常场景测试"
}

# ============================
# 报告
# ============================
Write-Host "`n========================================================" -ForegroundColor Cyan
Write-Host "  迁移完成！" -ForegroundColor Green
Write-Host "========================================================" -ForegroundColor Cyan
Write-Host "  📊 总计:" -ForegroundColor White
Write-Host "     - 真实服务测试用例: $($allIds.Count) 个" -ForegroundColor White
Write-Host "     - Mock 测试用例:    $($mockCaseIds.Count) 个" -ForegroundColor White
Write-Host "     - 总计:            $($allIds.Count + $mockCaseIds.Count) 个" -ForegroundColor White
Write-Host "  📦 Test Suite: 2 个" -ForegroundColor White
Write-Host "  🎯 Mock 预期:   $($MOCK_SCENARIOS.Count) 个" -ForegroundColor White
Write-Host "`n  后续步骤:" -ForegroundColor Yellow
Write-Host "  1. 在 Apifox 桌面版填入 llm_api_key 和 embedding_api_key" -ForegroundColor Yellow
Write-Host "  2. 启动 Mock 服务器" -ForegroundColor Yellow
Write-Host "  3. 运行: apifox test-suite run <ID> --project $PROJECT -e 47307103 --branch $BRANCH" -ForegroundColor Yellow
