--!strict
-- [[  VERSION 2  ]]
-- อัปเกรด:
-- 1. เพิ่มฟังก์ชัน `setAttributeIds`
-- 2. ใน Loop หลัก, สั่งให้ "ลองแทนที่" ทั้งใน Property และใน Attribute

-- (Path เหล่านี้ถูกต้องแล้ว ถ้ามันอยู่ใน "หัวใจ" เดียวกัน)
local ApiDump = require(script.Parent.ApiDump)
local retry = require(script.Parent.Retry)
local WaitGroup = require(script.Parent.WaitGroup)

local ScriptEditorService = game:GetService("ScriptEditorService")
local AssetService = game:GetService("AssetService")

local cachedClassProperties: { [string]: { string } } = {}

export type IdPair = {
    newId: number,
    oldId: number
}

-- (ฟังก์ชันลูกๆ ส่วนใหญ่เหมือนเดิม)
local function setScriptIds(scriptInstance: LuaSourceContainer, idsToChange: { IdPair })
    local source = scriptInstance.Source
    if not source then
        warn(scriptInstance, "has nil source")
        return
    end

    for _, idPair in idsToChange do
        local oldId = idPair.oldId
        local newId = idPair.newId
        source = string.gsub(source, `%f[%d]{oldId}%f[%D]`, tostring(newId))
    end

    if #source > 200_000 then
        ScriptEditorService:UpdateSourceAsync(scriptInstance, function() return source end)
    else
        scriptInstance.Source = source
    end
end

local function setAnimationId(animation: Animation, oldId: number, newId: number)
    animation.AnimationId = string.gsub(animation.AnimationId, tostring(oldId), tostring(newId)) 
end

local function setSoundId(sound: Sound, oldId: number, newId: number)
    sound.SoundId = string.gsub(sound.SoundId, tostring(oldId), tostring(newId))  
end

local function setNumberValueId(numValue: NumberValue | IntValue, oldId: number, newId: number)
    if numValue.Value == oldId then
        numValue.Value = newId
    end
end

local function setStringValueIds(strValue: StringValue, oldId: number, newId: number)
    strValue.Value = string.gsub(strValue.Value, tostring(oldId), tostring(newId)) 
end

local function setCharacterMesh(characterMesh: CharacterMesh, oldId: number, newId: number)
    if characterMesh.MeshId == oldId then
        characterMesh.MeshId = newId
    end
end

-- (ฟังก์ชัน transfer... เหมือนเดิม)
local function transferAttributes(oldInstance: Instance, newInstance: Instance)
    for name, value in oldInstance:GetAttributes() do
        newInstance:SetAttribute(name, value)
    end
end
local function transferTags(oldInstance: Instance, newInstance: Instance)
    for _, tag in oldInstance:GetTags() do
        newInstance:AddTag(tag)
    end
end
local function transferChildren(oldInstance: Instance, newInstance: Instance)
    for _, child in oldInstance:GetChildren() do
        if child:IsA("TouchTransmitter") then continue end
        child.Parent = newInstance
    end
end
local function transferProperties(oldInstance: Instance, newInstance: Instance)
    local className = oldInstance.ClassName
    if className ~= newInstance.ClassName then error(`oldInstance({className}) class is not equal to newInstance({newInstance.ClassName})`) end
    
    local success, apiDumpCached = pcall(ApiDump.isCached)
    if not success or not apiDumpCached then
        pcall(ApiDump.get) 
        if not ApiDump.isCached() then
             warn("ApiDump could not be fetched. Property transfer may be incomplete.")
             return
        end
    end

    local cachedProperties = cachedClassProperties[className]
    if not cachedProperties then
        cachedProperties = ApiDump.getProperties(className)
        cachedClassProperties[className] = cachedProperties
    end

    for _, property in cachedProperties do
        if property == "Parent" or property == "Sandboxed" or property == "brickColor" then continue end
        pcall(function()
            (newInstance :: any)[property] = (oldInstance :: any)[property]
        end)
    end
end
local function transferJoints(oldInstance: Instance, newInstance: Instance)
    for _, instance in game:GetDescendants() do
        if not instance:IsA("JointInstance") then continue end
        if instance.Part0 == oldInstance then
			instance.Part0 = newInstance
		elseif instance.Part1 == oldInstance then
			instance.Part1 = newInstance
		end
    end
end

local function setMeshPart(meshPart: MeshPart, oldId: number, newId: number)
    -- (เราจะตรวจสอบ MeshId ที่นี่ เพื่อป้องกันการแทนที่มั่ว)
    if not string.find(meshPart.MeshId, tostring(oldId)) then return end

    local contentRetrieved, content: Content = retry(3, Content.fromAssetId, newId) 
	if not contentRetrieved then
		warn(`failed to get content from {newId}, skipping {oldId}`)
        return
	end
    
    local newMeshPart = AssetService:CreateMeshPartAsync(content, {
        CollisionFidelity = meshPart.CollisionFidelity,
        RenderFidelity = meshPart.RenderFidelity,
        FluidFidelity = meshPart.FluidFidelity
    } :: any)

    local success, result = pcall(function()
        transferProperties(meshPart, newMeshPart)
        transferAttributes(meshPart, newMeshPart)
        transferTags(meshPart, newMeshPart)
        transferChildren(meshPart, newMeshPart)
        transferJoints(meshPart, newMeshPart)
    end)
    if not success then
        newMeshPart:Destroy()
        error(result)
    end

    newMeshPart.Parent = meshPart.Parent
    meshPart:Destroy()
end

local function setSpecialMesh(specialMesh: SpecialMesh, oldId: number, newId: number)
    specialMesh.MeshId = string.gsub(specialMesh.MeshId, tostring(oldId), tostring(newId))
end

local instanceIdSetters = {
    Animation = setAnimationId,
    Sound = setSoundId,
    NumberValue = setNumberValueId,
    IntValue = setNumberValueId,
    StringValue = getStringValueIds,
    CharacterMesh = setCharacterMesh,
    MeshPart = setMeshPart,
    SpecialMesh = setSpecialMesh,
}

-- ==========================================================
--  [[  ฟังก์ชันใหม่: แทนที่ใน Attributes  ]]
-- ==========================================================
local function setAttributeIds(instance: Instance, oldId: number, newId: number)
    -- ฟังก์ชันนี้จะตรวจสอบ Attributes ทั้งหมด ของ Instance ที่ส่งเข้ามา
    -- และแทนที่ ID ที่ตรงกัน
    for name, value in instance:GetAttributes() do
        if typeof(value) == "string" then
            -- ถ้าเป็น string, เช็คว่ามี oldId อยู่ข้างในไหม
            if string.find(value, tostring(oldId)) then
                local newValue = string.gsub(value, tostring(oldId), tostring(newId))
                instance:SetAttribute(name, newValue)
            end
        elseif typeof(value) == "number" then
            -- ถ้าเป็น number, เช็คว่ามันคือ oldId เลยหรือไม่
            if value == oldId then
                instance:SetAttribute(name, newId)
            end
        end
    end
end

-- ==========================================================
--  [[  ฟังก์ชันหลัก (แก้ไขใหม่)  ]]
-- ==========================================================
return function(filteredIds: { [number]: { Instance } }, idsToChange: { IdPair })
    local waitGroup = WaitGroup.new()
    local scriptIdChanges = {}

    for _, idPair in idsToChange do
        local oldId = idPair.oldId
        local newId = idPair.newId

        local instanceArray = filteredIds[oldId]
        if not instanceArray then continue end

        for _, instance in instanceArray do
            
            -- 1. (เหมือนเดิม) ตรวจสอบ Script Source
            if instance:IsA("LuaSourceContainer") then
                if not scriptIdChanges[instance] then scriptIdChanges[instance] = {} end
                table.insert(scriptIdChanges[instance], idPair)
                -- (ไม่ continue, เพราะ Script ก็มี Attribute ได้)
            end

            -- 2. (เหมือนเดิม) ตรวจสอบ Property มาตรฐาน
            local className = instance.ClassName
            local setInstanceId = instanceIdSetters[className]
            if setInstanceId then
                waitGroup:Add(function()
                    pcall(setInstanceId :: any, instance, oldId, newId)
                end)
            end
            
            -- 3. (ใหม่!) ตรวจสอบ Attributes ทั้งหมด
            -- (เราจะเรียกอันนี้กับ *ทุก* Instance ที่เจอ
            -- เพราะเราไม่รู้ว่า ID ที่เจอ มาจาก Property หรือ Attribute)
            waitGroup:Add(function()
                pcall(setAttributeIds, instance, oldId, newId)
            end)
        end
    end

    -- (ส่วนนี้เหมือนเดิม)
    for instance, idPairs in scriptIdChanges do
        waitGroup:Add(function()
            local success, result = pcall(setScriptIds, instance, idPairs)
            if not success then warn("Failed to bulk change", instance, result) end
        end)  
    end

    waitGroup:Wait()
end


