--!strict
-- [[  VERSION 2  ]]
-- อัปเกรด:
-- 1. สแกนแบบ Recursive (ดำดิ่ง) ทุกซอกทุกมุมของเกม
-- 2. เพิ่มการสแกน Attributes ของทุก Instance

local NUMBER_ONLY_FILTER = "%d+"

export type FilterOptions = {
    WhitelistedInstances: { string },
    Instances: { Instance }, -- (ตอนนี้จะเป็น {game})
}

-- (ฟังก์ชันลูกๆ เหมือนเดิม)
local function isValidId(id: number): boolean
	if id == 0 or id % 1 ~= 0 then return false end
	local idLength = math.floor(math.log10(math.abs(id))) + 1
	return idLength >= 7 and idLength <= 15
end

local function getId(filteredInstance: Instance, possibleId: any): { [number]: { Instance } }
    local id = tonumber(possibleId)
    if not id or not isValidId(id) then return {} end
    return { [id] = { filteredInstance } }
end

local function getStringIds(filteredInstance: Instance, str: string): { [number]: { Instance } }
    local idMap = {}
	for matchedString in string.gmatch(str, "%d+") do
		local id = tonumber(matchedString)
		if not id or idMap[id] or not isValidId(id) then continue end
		idMap[id] = { filteredInstance }
	end
    return idMap
end

local function getAnimationId(animation: Animation): { [number]: { Instance } }
    return getId(animation, string.match(animation.AnimationId, NUMBER_ONLY_FILTER))
end

local function getSoundId(sound: Sound): { [number]: { Instance } }
    return getId(sound, string.match(sound.SoundId, NUMBER_ONLY_FILTER))
end 

local function getScriptIds(scriptInstance: Script | LocalScript | ModuleScript): { [number]: { Instance } }
    return getStringIds(scriptInstance, scriptInstance.Source)
end

local function getStringValueIds(strValue: StringValue): { [number]: { Instance } }
    return getStringIds(strValue, strValue.Value)
end

local function getNumberValueId(numValue: NumberValue | IntValue): { [number]: { Instance } }
    return getId(numValue, numValue.Value)
end

local function getCharacterMesh(characterMesh: CharacterMesh): { [number]: { Instance } }
    return getId(characterMesh, characterMesh.MeshId)
end

local function getMeshPart(meshPart: MeshPart): { [number]: { Instance } }
    return getId(meshPart, string.match(meshPart.MeshId, NUMBER_ONLY_FILTER))
end

local function getSpecialMesh(specialMesh: SpecialMesh): { [number]: { Instance } }
    return getId(specialMesh, string.match(specialMesh.MeshId, NUMBER_ONLY_FILTER))
end

local instanceIdGetters: { [string]: (instance: any) -> { [number]: { Instance } } } = {
    Animation = getAnimationId,
    Sound = getSoundId,
    NumberValue = getNumberValueId,
    IntValue = getNumberValueId,
    StringValue = getStringValueIds,
    CharacterMesh = getCharacterMesh,
    MeshPart = getMeshPart,
    SpecialMesh = getSpecialMesh,
}

local function createFilterMap(instanceFilter: { string }): {[string]: (instance: Instance) -> { [number]: { Instance } }}
    local filterMap = {} :: any 
    for _, className in instanceFilter do
        if className == "LuaSourceContainer" then
            filterMap["LocalScript"] = getScriptIds
            filterMap["ModuleScript"] = getScriptIds
            filterMap["Script"] = getScriptIds
        else
            assert(instanceIdGetters[className], `{className} is not a supported instance`)
            filterMap[className] = instanceIdGetters[className]
        end
    end
    return filterMap
end

local function merge(originalIdMap: { [number]: { Instance } }, otherIdMap: { [number]: { Instance } })
    for id, instanceArray in otherIdMap do
        local idInstances = originalIdMap[id]
        if not idInstances then
            originalIdMap[id] = instanceArray
            continue
        end
        for _, instance in instanceArray do
            if table.find(idInstances, instance) then continue end
            table.insert(idInstances :: { any }, instance)
        end
    end
end

-- ==========================================================
--  [[  ฟังก์ชันหลัก (แก้ไขใหม่ทั้งหมด)  ]]
-- ==========================================================
return function(filterOptions: FilterOptions): { [number]: { Instance } }
    local idMap = {}
    local filterMap = createFilterMap(filterOptions.WhitelistedInstances)

    -- สร้างฟังก์ชันสแกนแบบ "ดำดิ่ง" (Recursive)
    local function scanInstance(instance: Instance)
        -- 1. (เหมือนเดิม) ตรวจสอบ ClassName ของ Instance นี้
        local className = instance.ClassName
        local parseId = filterMap[className]
        if parseId then
            merge(idMap, parseId(instance))
        end

        -- 2. (ใหม่!) ตรวจสอบ Attributes ทั้งหมดของ Instance นี้
        for name, value in instance:GetAttributes() do
            if typeof(value) == "string" then
                -- ถ้า Attribute เป็น string, ให้ค้นหา ID ที่ซ่อนอยู่ในนั้น
                merge(idMap, getStringIds(instance, value))
            elseif typeof(value) == "number" then
                -- ถ้า Attribute เป็น number, ให้ตรวจสอบว่ามันคือ ID หรือไม่
                merge(idMap, getId(instance, value))
            end
        end

        -- 3. (ใหม่!) สั่งให้สแกน "ลูก" ของ Instance นี้ต่อไป
        for _, child in instance:GetChildren() do
            -- (ใช้ pcall เพื่อความปลอดภัย เผื่อไปเจอที่ที่ไม่มีสิทธิ์)
            pcall(scanInstance, child) 
        end
    end

    -- เริ่มต้นสแกนจากจุดที่กำหนด (ปกติคือ "game")
    for _, rootInstance in filterOptions.Instances do
        scanInstance(rootInstance)
    end
    
    return idMap
end
