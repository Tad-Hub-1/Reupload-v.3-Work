-- PluginScript.server.luau
-- [[ V4.1 ]] Keyframe Reconstruction Mode
-- 1. ใช้ชื่อจาก Animation ในเกม
-- 2. แทนที่ ID เก่าด้วย ID ใหม่ทันที

local HttpService
local success, result = pcall(function()
    HttpService = game:GetService("HttpService")
end)
if not success then return end

local InsertService = game:GetService("InsertService")
local AssetIdFilter = require(script.AssetIdFilter) 
local Serializer = require(script.Serializer) -- ต้องมีไฟล์ Serializer นะ!

-- UI Setup (เหมือนเดิมเป๊ะ ย่อเพื่อความกระชับ)
local toolbar = plugin:CreateToolbar("Asset Reuploader V4")
local mainButton = toolbar:CreateButton("Open V4", "Open Panel", "")
local widget = plugin:CreateDockWidgetPluginGui("AssetReuploaderV4", DockWidgetPluginGuiInfo.new(Enum.InitialDockState.Float, true, false, 280, 450, 280, 400))
widget.Title = "Re-uploader V4 (Keyframes)"

local mainFrame = Instance.new("Frame", widget)
mainFrame.Size = UDim2.new(1,0,1,0)
mainFrame.BackgroundColor3 = Color3.fromRGB(40,40,40)
local layout = Instance.new("UIListLayout", mainFrame)
layout.HorizontalAlignment = Enum.HorizontalAlignment.Center
layout.Padding = UDim.new(0,5)
local padding = Instance.new("UIPadding", mainFrame)
padding.PaddingTop = UDim.new(0,10)

-- Elements
local function createTxt(text, order)
    local l = Instance.new("TextLabel", mainFrame)
    l.Text = text; l.Size = UDim2.new(1,0,0,20); l.BackgroundTransparency=1; l.TextColor3=Color3.new(1,1,1); l.LayoutOrder=order
    return l
end
createTxt("Python Server Port:", 1)
local portInput = Instance.new("TextBox", mainFrame)
portInput.Text="27000"; portInput.Size=UDim2.new(0.8,0,0,30); portInput.LayoutOrder=2

createTxt("Target Asset Type:", 3)
local typeBtn = Instance.new("TextButton", mainFrame)
typeBtn.Text="Animation"; typeBtn.Size=UDim2.new(0.8,0,0,30); typeBtn.BackgroundColor3=Color3.fromRGB(80,80,80); typeBtn.TextColor3=Color3.new(1,1,1); typeBtn.LayoutOrder=4

local startBtn = Instance.new("TextButton", mainFrame)
startBtn.Text="Start Reconstruction"; startBtn.Size=UDim2.new(0.9,0,0,40); startBtn.BackgroundColor3=Color3.fromRGB(0,160,80); startBtn.LayoutOrder=5
local statusLabel = createTxt("Ready.", 6)
statusLabel.Size = UDim2.new(0.9,0,0,100); statusLabel.TextWrapped=true

-- Logic
local currentTab = "Animation"
typeBtn.MouseButton1Click:Connect(function()
    if currentTab == "Animation" then currentTab = "Sound" else currentTab = "Animation" end
    typeBtn.Text = currentTab
end)

local isProcessing = false

startBtn.MouseButton1Click:Connect(function()
    if isProcessing then return end
    isProcessing = true
    startBtn.BackgroundColor3 = Color3.fromRGB(180,100,0)
    
    task.spawn(function()
        local port = portInput.Text
        local baseUrl = "http://localhost:" .. port
        
        -- 1. สแกนหา ID ทั้งหมด
        statusLabel.Text = "Scanning..."
        local filterOptions: AssetIdFilter.FilterOptions = {
            Instances = {game},
            WhitelistedInstances = {
                (currentTab == "Animation" and "Animation" or "Sound"),
                "LuaSourceContainer", "StringValue", "NumberValue", "IntValue"
            }
        }
        local filteredInstances = AssetIdFilter.filterInstances(filterOptions)
        
        -- 2. แปลงเป็น List
        local assetsToProcess = {}
        for oldId, instances in pairs(filteredInstances) do
            -- เอาชื่อจาก Instance ตัวแรกที่เจอ
            local name = "Asset_" .. tostring(oldId)
            if instances[1] then name = instances[1].Name end
            
            table.insert(assetsToProcess, { 
                oldId = oldId, 
                name = name, -- ส่งชื่อจริงไป
                instances = instances 
            })
        end
        
        if #assetsToProcess == 0 then
            statusLabel.Text = "No assets found."
            isProcessing = false
            startBtn.BackgroundColor3 = Color3.fromRGB(0,160,80)
            return
        end

        -- 3. เริ่ม Loop
        for i, item in ipairs(assetsToProcess) do
            local oldId = item.oldId
            local name = item.name
            
            statusLabel.Text = string.format("[%d/%d] Loading: %s (%d)", i, #assetsToProcess, name, oldId)
            
            -- 3.1 LoadAsset เพื่อดึง Keyframe
            local kfs = nil
            local successLoad, loadedModel = pcall(function()
                return InsertService:LoadAsset(oldId)
            end)
            
            if successLoad and loadedModel then
                kfs = loadedModel:FindFirstChildWhichIsA("KeyframeSequence", true)
            end
            
            if not kfs then
                statusLabel.Text = string.format("FAILED to load ID %d (403/Deleted). Skipping.", oldId)
                warn("LoadAsset failed for", oldId)
            else
                -- 3.2 Serialize ข้อมูล
                statusLabel.Text = "Extracting Data..."
                local kfsData = Serializer.serialize(kfs)
                loadedModel:Destroy()
                
                -- 3.3 ส่งไป Python (Builder)
                local payload = {
                    oldId = oldId,
                    name = name, -- ใช้ชื่อจากในเกม
                    kfsData = kfsData
                }
                
                local json = HttpService:JSONEncode(payload)
                local successPost, response = pcall(function()
                    return HttpService:PostAsync(baseUrl .. "/api/reupload_data", json, Enum.HttpContentType.ApplicationJson)
                end)
                
                if successPost then
                    local resData = HttpService:JSONDecode(response)
                    if resData.status == "ok" then
                        local newId = resData.newId
                        statusLabel.Text = string.format("SUCCESS: %s (%d -> %d)", name, oldId, newId)
                        
                        -- 3.4 แทนที่ทันที!
                        local idPairList = {{ oldId = oldId, newId = newId }}
                        AssetIdFilter.replaceIds(filteredInstances, idPairList)
                    else
                        statusLabel.Text = "Server Error: " .. tostring(resData.error)
                    end
                else
                    statusLabel.Text = "Connection Error. Check Python Console."
                end
            end
            task.wait(0.2)
        end
        
        statusLabel.Text = "All Done!"
        isProcessing = false
        startBtn.BackgroundColor3 = Color3.fromRGB(0,160,80)
    end)
end)

mainButton.Click:Connect(function() widget.Enabled = not widget.Enabled end)
