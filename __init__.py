bl_info = {
    "name": "Better Baker",
    "author": "Your Name",
    "version": (2, 0),
    "blender": (4, 0, 0),
    "location": "View3D > Sidebar > Better Baker",
    "description": "Multi-map queue baking engine with non-blocking UI layout windows",
    "category": "Render",
}

import bpy
from .bake_engine import bake_single_map

# --- OPERATOR: EXECUTE MODAL BACKGROUND QUEUE BAKE ---
class BAKER_OT_render_bake(bpy.types.Operator):
    """Execute the baking process with a live progress bar"""
    bl_idname = "better_baker.render_bake"
    bl_label = "Render"
    bl_options = {'REGISTER', 'UNDO'}
    
    _timer = None
    images_to_show = []
    current_index = 0
    total_maps = 0

    def modal(self, context, event):
        scene = context.scene
        wm = context.window_manager

        if event.type == 'TIMER':
            # Handle Final Completion Wrap Up
            if self.current_index >= self.total_maps:
                wm.progress_end()
                main_window = context.window
                
                # STAGGERED PREVIEW WINDOWS
                for img in self.images_to_show:
                    if img:
                        bpy.ops.screen.userpref_show('INVOKE_DEFAULT')
                        new_window = wm.windows[-1]
                        if new_window.screen and new_window.screen.areas:
                            area = new_window.screen.areas[0]
                            area.type = 'IMAGE_EDITOR'
                            area.spaces.active.image = img
                
                # Restore system and focus controls
                context.window_manager.windows[0].screen = main_window.screen
                context.window.cursor_set("DEFAULT")
                
                self.report({'INFO'}, "Baking completed successfully!")
                wm.event_timer_remove(self._timer)
                return {'FINISHED'}

            # Run Singular Map Bake Step Execution Loop
            texture_item = scene.better_baker_textures[self.current_index]
            wm.progress_update(self.current_index)
            
            try:
                baked_img = bake_single_map(
                    texture_item=texture_item,
                    resolution_mode=scene.better_baker_settings.texture_size,
                    settings=scene.better_baker_settings,
                    prefix=scene.better_baker_settings.prefix
                )
                if baked_img:
                    self.images_to_show.append(baked_img)
            except Exception as e:
                self.report({'ERROR'}, f"Baking failed at {texture_item.name}: {str(e)}")
                wm.progress_end()
                wm.event_timer_remove(self._timer)
                context.window.cursor_set("DEFAULT")
                return {'CANCELLED'}

            self.current_index += 1

        return {'RUNNING_MODAL'}

    def execute(self, context):
        scene = context.scene
        wm = context.window_manager
        
        if not scene.better_baker_textures:
            self.report({'WARNING'}, "Your texture baking list is empty!")
            return {'CANCELLED'}
            
        self.images_to_show = []
        self.current_index = 0
        self.total_maps = len(scene.better_baker_textures)
        
        wm.progress_begin(0, self.total_maps)
        context.window.cursor_set("WAIT")
        
        # Micro loop ticks every 0.1 seconds to yield GUI processing frames
        self._timer = wm.event_timer_add(0.1, window=context.window)
        wm.modal_handler_add(self)
        
        return {'RUNNING_MODAL'}


# --- MENU: TEXTURE DROPDOWN LIST OPTION SELECTION ---
class BAKER_MT_texture_select_menu(bpy.types.Menu):
    bl_label = "Select Texture Map"
    bl_idname = "BAKER_MT_texture_select_menu"

    def draw(self, context):
        layout = self.layout
        layout.operator("better_baker.add_texture", text="Base Color").texture_type = "Base Color"
        layout.operator("better_baker.add_texture", text="Roughness").texture_type = "Roughness"
        layout.operator("better_baker.add_texture", text="Metallic").texture_type = "Metallic"
        layout.operator("better_baker.add_texture", text="Normal").texture_type = "Normal"
        layout.operator("better_baker.add_texture", text="Clearcoat Weight").texture_type = "Clearcoat Weight"
        layout.operator("better_baker.add_texture", text="Clearcoat Roughness").texture_type = "Clearcoat Roughness"
        layout.operator("better_baker.add_texture", text="Emission Color").texture_type = "Emission Color"
        layout.operator("better_baker.add_texture", text="Emission Strength").texture_type = "Emission Strength"
        layout.operator("better_baker.add_texture", text="Transmission Weight").texture_type = "Transmission Weight"
        layout.operator("better_baker.add_texture", text="Subsurface Weight").texture_type = "Subsurface Weight"
        layout.operator("better_baker.add_texture", text="Specular IOR Level").texture_type = "Specular IOR Level"
        layout.operator("better_baker.add_texture", text="Alpha").texture_type = "Alpha"


# --- EXTRA COMPONENT STUBS FOR COMPILATION RESTRAINTS ---
class BAKER_IT_texture_item(bpy.types.PropertyGroup):
    name: bpy.props.StringProperty(name="Map Name")

class BAKER_ST_settings(bpy.types.PropertyGroup):
    prefix: bpy.props.StringProperty(name="Prefix", default="Baked")
    custom_width: bpy.props.IntProperty(name="Custom Width", default=2048, min=1)
    texture_size: bpy.props.EnumProperty(
        name="Size",
        items=[('1K', '1K', ''), ('2K', '2K', ''), ('4K', '4K', ''), ('8K', '8K', ''), ('CUSTOM', 'Custom', '')],
        default='2K'
    )

class BAKER_OT_add_texture(bpy.types.Operator):
    bl_idname = "better_baker.add_texture"
    bl_label = "Add Texture Map"
    texture_type: bpy.props.StringProperty()
    
    def execute(self, context):
        item = context.scene.better_baker_textures.add()
        item.name = self.texture_type
        return {'FINISHED'}

class BAKER_PT_sidebar_panel(bpy.types.Panel):
    bl_label = "Better Baker Engine"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Better Baker'

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        
        layout.prop(scene.better_baker_settings, "prefix")
        layout.prop(scene.better_baker_settings, "texture_size")
        if scene.better_baker_settings.texture_size == 'CUSTOM':
            layout.prop(scene.better_baker_settings, "custom_width")
            
        layout.menu("BAKER_MT_texture_select_menu", text="Add Map To Queue...")
        
        box = layout.box()
        for idx, item in enumerate(scene.better_baker_textures):
            row = box.row()
            row.label(text=item.name)
            
        layout.separator()
        layout.operator("better_baker.render_bake", icon='RENDER_STILL')


# --- REGISTRATION CORE FLOW ---
classes = (
    BAKER_IT_texture_item,
    BAKER_ST_settings,
    BAKER_OT_add_texture,
    BAKER_OT_render_bake,
    BAKER_MT_texture_select_menu,
    BAKER_PT_sidebar_panel,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.better_baker_textures = bpy.props.CollectionProperty(type=BAKER_IT_texture_item)
    bpy.types.Scene.better_baker_settings = bpy.props.PointerProperty(type=BAKER_ST_settings)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    del bpy.types.Scene.better_baker_textures
    del bpy.types.Scene.better_baker_settings

if __name__ == "__main__":
    register()