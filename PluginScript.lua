-- PluginScript.server.luau
-- [[  V3 - อัปเกรด  ]]
-- 1. เพิ่มปุ่ม Toggle "Check Existing"
-- 2. ส่งค่า "check_existing" (true/false) ไปให้ Python Server
-- 3. [แก้ไข] เปลี่ยน URL endpoint เป็น "/api/reupload_single" (ตาม Python script ใหม่)

-- 1. Services
local HttpService
local success, result = pcall(function()
    HttpService = game:GetService("HttpService")
end)
if not success then
    warn("[Reuploader Plugin] ERROR: HttpService is not available or enabled! " .. result)
    return
end

local CoreGui = game:GetService("CoreGui")

-- 2. โหลด "สมอง" (จาก "ลูก" ที่อยู่ข้างใน)
local AssetIdFilter = require(script.AssetIdFilter) 
if not AssetIdFilter then
    warn("[Reuploader Plugin] ERROR: ไม่พบ Module 'AssetIdFilter' ที่อยู่ข้างใน!")
    return
end

-- 3. ตัวแปรสถานะ
local currentTab = "Animation"
local isProcessing = false
local checkExisting = false -- <--- [ใหม่] สถานะของปุ่ม Toggle (ค่าเริ่มต้นคือ "ปิด")

-- 4. สร้างปุ่ม Toolbar
local toolbar = plugin:CreateToolbar("Asset Reuploader V3")
local mainButton = toolbar:CreateButton(
    "Open Re-uploader",
    "Open the asset re-uploader panel",
    ""
)

-- 5. สร้าง GUI (หน้าต่างหลัก)
local widget = plugin:CreateDockWidgetPluginGui(
    "AssetReuploaderV3",
    DockWidgetPluginGuiInfo.new(
        Enum.InitialDockState.Float,
        true, -- Enabled
        false, -- OverridePoV
        280,   -- Width
        450,   -- Height (เพิ่มความสูง)
        280,   -- MinWidth
        400    -- MinHeight
    )
)
widget.Title = "Live Re-uploader V3"

-- 6. สร้างองค์ประกอบ GUI
-- [[ Main Frame ]]
local mainFrame = Instance.new("Frame")
mainFrame.Size = UDim2.new(1, 0, 1, 0)
mainFrame.BackgroundColor3 = Color3.fromRGB(40, 40, 40)
mainFrame.Parent = widget

local layout = Instance.new("UIListLayout")
layout.Padding = UDim.new(0, 5)
layout.SortOrder = Enum.SortOrder.LayoutOrder
layout.HorizontalAlignment = Enum.HorizontalAlignment.Center
layout.Parent = mainFrame

local padding = Instance.new("UIPadding")
padding.PaddingTop = UDim.new(0, 10)
padding.PaddingLeft = UDim.new(0, 10)
padding.PaddingRight = UDim.new(0, 10)
padding.Parent = mainFrame

-- [[ Title ]]
local titleLabel = Instance.new("TextLabel")
titleLabel.Size = UDim2.new(1, 0, 0, 20)
titleLabel.Text = "Roblox Live Re-uploader"
titleLabel.Font = Enum.Font.SourceSansBold
titleLabel.TextSize = 18
titleLabel.TextColor3 = Color3.fromRGB(255, 255, 255)
titleLabel.BackgroundTransparency = 1
titleLabel.LayoutOrder = 1
titleLabel.Parent = mainFrame

-- [[ Port Input ]]
local portLabel = Instance.new("TextLabel")
portLabel.Size = UDim2.new(1, 0, 0, 15)
portLabel.Text = "Python Server Port:"
portLabel.Font = Enum.Font.SourceSans
portLabel.TextSize = 14
portLabel.TextColor3 = Color3.fromRGB(180, 180, 180)
portLabel.TextXAlignment = Enum.TextXAlignment.Left
portLabel.BackgroundTransparency = 1
portLabel.LayoutOrder = 2
portLabel.Parent = mainFrame

local portInput = Instance.new("TextBox")
portInput.Name = "PortInput"
portInput.Size = UDim2.new(1, 0, 0, 30)
portInput.BackgroundColor3 = Color3.fromRGB(30, 30, 30)
portInput.TextColor3 = Color3.fromRGB(0, 255, 127)
portInput.Font = Enum.Font.Code
portInput.TextSize = 16
portInput.Text = "27000" -- ค่าเริ่มต้น
portInput.PlaceholderText = "ป้อน Port จาก Python"
portInput.LayoutOrder = 3
portInput.Parent = mainFrame

-- [[ Tab Buttons ]]
local tabFrame = Instance.new("Frame")
tabFrame.Size = UDim2.new(1, 0, 0, 30)
tabFrame.BackgroundTransparency = 1
tabFrame.LayoutOrder = 4
tabFrame.Parent = mainFrame

local tabLayout = Instance.new("UIListLayout")
tabLayout.FillDirection = Enum.FillDirection.Horizontal
tabLayout.VerticalAlignment = Enum.VerticalAlignment.Center
tabLayout.HorizontalAlignment = Enum.HorizontalAlignment.Center
tabLayout.SortOrder = Enum.SortOrder.LayoutOrder
tabLayout.Parent = tabFrame

local animButton = Instance.new("TextButton")
animButton.Name = "AnimButton"
animButton.Size = UDim2.new(0.5, -2, 1, 0)
animButton.Text = "Animation"
animButton.Font = Enum.Font.SourceSansBold
animButton.TextSize = 16
animButton.TextColor3 = Color3.fromRGB(255, 255, 255)
animButton.BackgroundColor3 = Color3.fromRGB(80, 80, 80) -- สี Active
animButton.Parent = tabFrame

local soundButton = Instance.new("TextButton")
soundButton.Name = "SoundButton"
soundButton.Size = UDim2.new(0.5, -2, 1, 0)
soundButton.Text = "Sound"
soundButton.Font = Enum.Font.SourceSansBold
soundButton.TextSize = 16
soundButton.TextColor3 = Color3.fromRGB(150, 150, 150) -- สี Inactive
soundButton.BackgroundColor3 = Color3.fromRGB(50, 50, 50)
soundButton.Parent = tabFrame

-- [[  ปุ่ม Toggle (ใหม่)  ]]
local checkExistingToggle = Instance.new("TextButton")
checkExistingToggle.Name = "CheckExistingToggle"
checkExistingToggle.Size = UDim2.new(1, 0, 0, 30)
checkExistingToggle.BackgroundColor3 = Color3.fromRGB(180, 50, 50) -- สีแดง (OFF)
checkExistingToggle.TextColor3 = Color3.fromRGB(255, 255, 255)
checkExistingToggle.Font = Enum.Font.SourceSansBold
checkExistingToggle.TextSize = 14
checkExistingToggle.Text = "Check Existing: OFF (Re-upload เลย)"
checkExistingToggle.LayoutOrder = 5
checkExistingToggle.Parent = mainFrame

local toggleHint = Instance.new("TextLabel")
toggleHint.Size = UDim2.new(1, 0, 0, 15)
toggleHint.Text = "(ใช้ได้เฉพาะเมื่อรัน Python ด้วย Cookie)"
toggleHint.Font = Enum.Font.SourceSansItalic
toggleHint.TextSize = 12
toggleHint.TextColor3 = Color3.fromRGB(150, 150, 150)
toggleHint.TextXAlignment = Enum.TextXAlignment.Left
toggleHint.BackgroundTransparency = 1
toggleHint.LayoutOrder = 6
toggleHint.Parent = mainFrame


-- [[ Start Button ]]
local startButton = Instance.new("TextButton")
startButton.Name = "StartButton"
startButton.Size = UDim2.new(1, 0, 0, 40)
startButton.BackgroundColor3 = Color3.fromRGB(0, 160, 80)
startButton.TextColor3 = Color3.fromRGB(255, 255, 255)
startButton.Font = Enum.Font.SourceSansBold
startButton.TextSize = 18
startButton.Text = "Start Re-upload (Animation)"
startButton.LayoutOrder = 7
startButton.Parent = mainFrame

-- [[ Status Label ]]
local statusLabel = Instance.new("TextLabel")
statusLabel.Name = "StatusLabel"
statusLabel.Size = UDim2.new(1, 0, 1, -200) -- ปรับขนาดตาม UI ใหม่
statusLabel.Text = "Ready. (Run Python server first)"
statusLabel.Font = Enum.Font.SourceSans
statusLabel.TextSize = 14
statusLabel.TextColor3 = Color3.fromRGB(200, 200, 200)
statusLabel.BackgroundTransparency = 1
statusLabel.TextWrapped = true
statusLabel.TextYAlignment = Enum.TextYAlignment.Top
statusLabel.TextXAlignment = Enum.TextXAlignment.Left
statusLabel.LayoutOrder = 8
statusLabel.Parent = mainFrame

-- 7. Logic การทำงาน
local function updateTab(selectedTab)
    currentTab = selectedTab
    if selectedTab == "Animation" then
        animButton.BackgroundColor3 = Color3.fromRGB(80, 80, 80)
        animButton.TextColor3 = Color3.fromRGB(255, 255, 255)
        soundButton.BackgroundColor3 = Color3.fromRGB(50, 50, 50)
        soundButton.TextColor3 = Color3.fromRGB(150, 150, 150)
        startButton.Text = "Start Re-upload (Animation)"
    else
        soundButton.BackgroundColor3 = Color3.fromRGB(80, 80, 80)
        soundButton.TextColor3 = Color3.fromRGB(255, 255, 255)
        animButton.BackgroundColor3 = Color3.fromRGB(50, 50, 50)
        animButton.TextColor3 = Color3.fromRGB(150, 150, 150)
        startButton.Text = "Start Re-upload (Sound)"
    end
end

animButton.MouseButton1Click:Connect(function()
    if isProcessing then return end
    updateTab("Animation")
end)

soundButton.MouseButton1Click:Connect(function()
    if isProcessing then return end
    updateTab("Sound")
end)

-- [[  Logic ปุ่ม Toggle (ใหม่)  ]]
checkExistingToggle.MouseButton1Click:Connect(function()
    if isProcessing then return end
    
    checkExisting = not checkExisting -- สลับค่า
    
    if checkExisting then
        checkExistingToggle.Text = "Check Existing: ON (ค้นหาก่อน)"
        checkExistingToggle.BackgroundColor3 = Color3.fromRGB(50, 180, 50) -- สีเขียว
    else
        checkExistingToggle.Text = "Check Existing: OFF (Re-upload เลย)"
        checkExistingToggle.BackgroundColor3 = Color3.fromRGB(180, 50, 50) -- สีแดง
    end
end)


-- [[ ฟังก์ชันหลัก: เมื่อกดปุ่ม Start ]]
startButton.MouseButton1Click:Connect(function()
    if isProcessing then return end
    isProcessing = true
    startButton.Text = "Processing..."
    startButton.BackgroundColor3 = Color3.fromRGB(180, 100, 0)
    statusLabel.Text = "Starting..."

    task.spawn(function()
        local port = portInput.Text
        if not port or not port:match("%d+") then
            statusLabel.Text = "ERROR: Invalid Port Number."
            isProcessing = false
            return
        end
        
        local baseUrl = "http://localhost:" .. port
        local assetType = currentTab
        local checkExistingState = checkExisting -- <--- [ใหม่] อ่านค่า Toggle 1 ครั้งก่อนเริ่ม
        
        -- 1. ตั้งค่าการค้นหา
        local filterOptions: AssetIdFilter.FilterOptions = {
            Instances = {game},
            WhitelistedInstances = {
                (assetType == "Animation" and "Animation" or "Sound"),
                "LuaSourceContainer", 
                "StringValue", "NumberValue", "IntValue" 
            }
        }
        
        statusLabel.Text = string.format("Scanning for all '%s' assets in the game...", assetType)
        
        -- 2. ค้นหา Asset ทั้งหมด (เรียก "สมอง")
        local filteredInstances = AssetIdFilter.filterInstances(filterOptions)
        
        -- แปลงผลลัพธ์เป็น List ที่จะส่งไป Python
        local assetsToProcess = {}
        for oldId, instances in pairs(filteredInstances) do
            local firstInstance = instances[1]
            if firstInstance then
                table.insert(assetsToProcess, {
                    oldId = oldId,
                    name = string.format("%s_%s", assetType, firstInstance.Name),
                    type = assetType,
                    check_existing = checkExistingState -- <--- [ใหม่] ส่งสถานะ Toggle ไปด้วย
                })
            end
        end
        
        if #assetsToProcess == 0 then
            statusLabel.Text = "No assets found to process."
            isProcessing = false
            startButton.Text = "Start Re-upload (" .. assetType .. ")"
            startButton.BackgroundColor3 = Color3.fromRGB(0, 160, 80)
            return
        end

        statusLabel.Text = string.format("Found %d assets. Starting re-upload process...", #assetsToProcess)
        
        local successCount = 0
        local failCount = 0
        
        -- 3. วน Loop ส่ง Request ทีละอัน
        for i, assetData in ipairs(assetsToProcess) do
            local oldId = assetData.oldId
            local assetName = assetData.name
            
            statusLabel.Text = string.format("[%d/%d] Processing %s: %s (ID: %d)",
                i, #assetsToProcess, assetType, assetName, oldId)
                
            local requestBody = HttpService:JSONEncode(assetData)
            
            -- [[  แก้ไข Endpoint  ]]
            -- ส่ง Request ไปหา Python Server (Endpoint ใหม่: /api/reupload_single)
            local success, response = pcall(function()
                return HttpService:PostAsync(baseUrl .. "/api/reupload_single", requestBody, Enum.HttpContentType.ApplicationJson)
            end)
            
            if not success then
                statusLabel.Text = string.format("[%d/%d] FAILED: %s. Is Python server running on port %s?", i, #assetsToProcess, assetName, port)
                warn("PostAsync Error:", response)
                failCount += 1
                continue 
            end
            
            -- 4. รับผลลัพธ์จาก Python
            local responseData
            local decodeSuccess, decodeResult = pcall(function()
                responseData = HttpService:JSONDecode(response)
            end)

            if not decodeSuccess then
                 statusLabel.Text = string.format("[%d/%d] FAILED: %s (Could not decode server response)", i, #assetsToProcess, assetName)
                 warn("JSONDecode Error:", decodeResult)
                 failCount += 1
                 continue
            end
            
            if responseData.status == "ok" then
                local newId = responseData.newId
                
                if responseData.skipped then
                    statusLabel.Text = string.format("[%d/%d] SKIPPED: %s. Using existing ID: %d",
                        i, #assetsToProcess, assetName, newId)
                else
                    statusLabel.Text = string.format("[%d/%d] SUCCESS: %s. Replacing %d -> %d",
                        i, #assetsToProcess, assetName, oldId, newId)
                end
                
                -- 5. เรียก "สมอง" ให้แทนที่ ID
                local idPairList = {{ oldId = oldId, newId = newId }}
                AssetIdFilter.replaceIds(filteredInstances, idPairList)
                
                successCount += 1
            else
                statusLabel.Text = string.format("[%d/%d] FAILED: %s (Server Error: %s)",
                    i, #assetsToProcess, assetName, responseData.error or "Unknown")
                warn("Server Error:", responseData.error)
                failCount += 1
            end
            
            task.wait(0.1) -- พักเล็กน้อย
        end
        
        -- 6. เสร็จสิ้น
        statusLabel.Text = string.format("COMPLETE! Success: %d, Failed: %d", successCount, failCount)
        isProcessing = false
        startButton.Text = "Start Re-upload (" .. assetType .. ")"
        startButton.BackgroundColor3 = Color3.fromRGB(0, 160, 80)
        
    end)
end)

-- 8. Logic การเปิด/ปิด GUI
mainButton.Click:Connect(function()
    widget.Enabled = not widget.Enabled
end)

widget:BindToClose(function()
    widget.Enabled = false
end)
