--!strict
-- Serializer.luau: แกะข้อมูล KeyframeSequence เป็น Table เพื่อส่งให้ Python
local Serializer = {}

local function serializePose(pose: Pose)
    local cf = pose.CFrame
    local data = {
        Name = pose.Name,
        Weight = pose.Weight,
        EasingStyle = pose.EasingStyle.Value,
        EasingDirection = pose.EasingDirection.Value,
        -- ส่ง CFrame เป็น Array 12 ตัวเลข
        CFrame = {cf:GetComponents()},
        SubPoses = {}
    }
    
    for _, sub in pose:GetSubPoses() do
        table.insert(data.SubPoses, serializePose(sub))
    end
    
    return data
end

function Serializer.serialize(kfs: KeyframeSequence)
    local data = {
        Name = kfs.Name,
        Loop = kfs.Loop,
        Priority = kfs.Priority.Value,
        Keyframes = {}
    }
    
    -- เรียง Keyframe ตามเวลา
    local keyframes = kfs:GetKeyframes()
    table.sort(keyframes, function(a, b) return a.Time < b.Time end)
    
    for _, kf in keyframes do
        local kfData = {
            Name = kf.Name,
            Time = kf.Time,
            Poses = {}
        }
        
        for _, pose in kf:GetPoses() do
            table.insert(kfData.Poses, serializePose(pose))
        end
        
        table.insert(data.Keyframes, kfData)
    end
    
    return data
end

return Serializer
