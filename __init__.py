bl_info = {
    "name": "The Better Baker",
    "author": "Chaim Mendes",
    "version": (1, 0),
    "blender": (4, 2, 0),
    "location": "Properties > Render > The Better Baker",
    "description": "A no nonsense, reliable PBR baker that focuses on working.",
    "category": "Render",
}

import bpy
import bpy.utils.previews

from .bake_engine import betterbakerengine
# --- 1. PROPERTY DEFINITIONS ---
class BetterBakerSettings(bpy.types.PropertyGroup):
    texture_size: bpy.props.EnumProperty(
        name="Texture Size",
        items=[
            ('1K', "1K", "1024 x 1024"),
            ('2K', "2K", "2048 x 2048"),
            ('4K', "4K", "4096 x 4096"),
            ('8K', "8K", "8192 x 8192"),
            ('CUSTOM', "Custom", "Specify a custom resolution"),
        ],
        default='2K'
    )
    
    custom_width: bpy.props.IntProperty(
        name="Width", default=2048, min=16, max=16384
    )
    custom_height: bpy.props.IntProperty(
        name="Height", default=2048, min=16, max=16384
    )
    prefix: bpy.props.StringProperty(
        name="Prefix", default="T_"
    )


class BetterBakerTextureItem(bpy.types.PropertyGroup):
    name: bpy.props.StringProperty(name="Texture Type")


# --- 2. OPERATORS ---
class BAKER_OT_add_texture_type(bpy.types.Operator):
    """Add a texture type to the baking queue"""
    bl_idname = "better_baker.add_texture"
    bl_label = "Add Texture"
    bl_options = {'REGISTER', 'UNDO'}
    
    texture_type: bpy.props.StringProperty()

    def execute(self, context):
        scene = context.scene
        
        # Check if this texture type is already in the list to avoid duplicates
        for item in scene.better_baker_textures:
            if item.name == self.texture_type:
                self.report({'WARNING'}, f"{self.texture_type} is already in the list!")
                return {'CANCELLED'}
                
        item = scene.better_baker_textures.add()
        item.name = self.texture_type
        
        # Force the list index to select the newest item
        scene.better_baker_idx = len(scene.better_baker_textures) - 1
        return {'FINISHED'}


class BAKER_OT_remove_texture_type(bpy.types.Operator):
    """Remove the selected texture type from the queue"""
    bl_idname = "better_baker.remove_texture"
    bl_label = "Remove Texture"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        scene = context.scene
        index = scene.better_baker_idx
        
        if index >= 0 and index < len(scene.better_baker_textures):
            scene.better_baker_textures.remove(index)
            scene.better_baker_idx = max(0, index - 1)
        return {'FINISHED'}


class BAKER_OT_render_bake(bpy.types.Operator):
    """Execute the baking process"""
    bl_idname = "better_baker.render_bake"
    bl_label = "Render"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        scene = context.scene
        
        # Check if the user actually added any textures to the list first
        if not scene.better_baker_textures:
            self.report({'WARNING'}, "Your texture baking list is empty!")
            return {'CANCELLED'}
            
        try:
            # We pass the collection, the raw size string enum, the full settings group, and the text prefix
            success = betterbakerengine(
                textures_list=scene.better_baker_textures, 
                resolution_mode=scene.better_baker_settings.texture_size, 
                settings=scene.better_baker_settings,
                prefix=scene.better_baker_settings.prefix
            )
            
            if success:
                self.report({'INFO'}, "Baking completed successfully!")
                
        except Exception as e:
            self.report({'ERROR'}, f"Baking failed: {str(e)}")
            return {'CANCELLED'}
            
        return {'FINISHED'}

# --- 3. UI LIST DRAW CLASS (The Missing Link) ---
class BAKER_UL_texture_list(bpy.types.UIList):
    """This class explicitly dictates how items are drawn inside the text box row"""
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        # We display the name of the item alongside a clean texture icon
        layout.label(text=item.name, icon='IMAGE_DATA')


# --- 4. THE MAIN UI PANEL ---
class RENDER_PT_custom_bake_tools(bpy.types.Panel):
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = 'render'
    bl_label = "The Better Baker"
    
    @classmethod
    def poll(cls, context):
        return context.engine == 'CYCLES'

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        settings = scene.better_baker_settings

        # Texture Size Buttons
        layout.label(text="Texture Size:")
        row = layout.row(align=True)
        row.prop(settings, "texture_size", expand=True)

        if settings.texture_size == 'CUSTOM':
            box = layout.box()
            col = box.column(align=True)
            col.prop(settings, "custom_width", text="Width (px)")
            col.prop(settings, "custom_height", text="Height (px)")

        layout.separator()

        # Prefix Field
        layout.prop(settings, "prefix")

        layout.separator()

        # Textures List Box
        layout.label(text="Textures:")
        
        row = layout.row()
        # We point template_list directly to our new 'BAKER_UL_texture_list' class layout
        row.template_list(
            "BAKER_UL_texture_list", "", 
            scene, "better_baker_textures", 
            scene, "better_baker_idx"
        )
        
        col = row.column(align=True)
        col.menu("BAKER_MT_texture_select_menu", icon='ADD', text="")
        col.operator("better_baker.remove_texture", icon='REMOVE', text="")

        layout.separator(factor=2)

        # Big Render Button
        layout.scale_y = 1.5
        layout.operator("better_baker.render_bake", icon='RENDER_STILL')


# --- 5. HELPER MENUS ---
class BAKER_MT_texture_select_menu(bpy.types.Menu):
    bl_label = "Select Texture Map"

    def draw(self, context):
        layout = self.layout
        layout.operator("better_baker.add_texture", text="Base Color").texture_type = "Base Color"
        layout.operator("better_baker.add_texture", text="Roughness").texture_type = "Roughness"
        layout.operator("better_baker.add_texture", text="Metallic").texture_type = "Metallic"
        layout.operator("better_baker.add_texture", text="Normal").texture_type = "Normal"
        layout.operator("better_baker.add_texture", text="Ambient Occlusion").texture_type = "Ambient Occlusion"
        layout.operator("better_baker.add_texture", text="Emissive").texture_type = "Emissive"


# --- 6. REGISTER REGION ---
preview_collections = {}
classes = (
    BetterBakerSettings,
    BetterBakerTextureItem,
    BAKER_OT_add_texture_type,
    BAKER_OT_remove_texture_type,
    BAKER_OT_render_bake,
    BAKER_UL_texture_list,       # Registered the UI List draw rules
    BAKER_MT_texture_select_menu,
    RENDER_PT_custom_bake_tools,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
        
    bpy.types.Scene.better_baker_settings = bpy.props.PointerProperty(type=BetterBakerSettings)
    bpy.types.Scene.better_baker_textures = bpy.props.CollectionProperty(type=BetterBakerTextureItem)
    bpy.types.Scene.better_baker_idx = bpy.props.IntProperty(default=0)

    pcoll = bpy.utils.previews.new()
    preview_collections["main"] = pcoll

def unregister():
    for pcoll in list(preview_collections.values()):
        bpy.utils.previews.remove(pcoll)
    preview_collections.clear()

    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
        
    del bpy.types.Scene.better_baker_settings
    del bpy.types.Scene.better_baker_textures
    del bpy.types.Scene.better_baker_idx

if __name__ == "__main__":
    register()