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
<<<<<<< HEAD
    """Execute the baking process asynchronously with real-time UI updates"""
=======
    """Execute the baking process with a live progress bar"""
>>>>>>> c5e196d721033f9de01f0df524ad775c0903720b
    bl_idname = "better_baker.render_bake"
    bl_label = "Render"
    
    _timer = None
<<<<<<< HEAD
    _queue = []
    _total_maps = 0

    def modal(self, context, event):
        scene = context.scene
        settings = scene.better_baker_settings

        if event.type == 'TIMER':
            # Safe completion sequence
            if not self._queue:
                context.area.tag_redraw()
                self.report({'INFO'}, "Baking completed successfully!")
                return self.cancel(context)

            # Pop the next texture item off the processing sequence
            current_item = self._queue.pop(0)
            processed_count = self._total_maps - len(self._queue) - 1
            context.area.tag_redraw()

            try:
                # Process single pass execution
                bake_image = betterbakerengine([current_item], settings.texture_size, settings, settings.prefix)
                
                # Dynamic Image Viewer window spawning logic
                if bake_image:
                    bpy.ops.wm.window_new()
                    new_win = context.window_manager.windows[-1]
                    for area in new_win.screen.areas:
                        if area.type in {'VIEW_3D', 'EMPTY'}:
                            area.type = 'IMAGE_EDITOR'
                            area.spaces.active.image = bake_image
                            break

            except Exception as e:
                self.report({'ERROR'}, f"Baking run encountered an error: {str(e)}")
                return self.cancel(context)
=======
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
>>>>>>> c5e196d721033f9de01f0df524ad775c0903720b

        return {'RUNNING_MODAL'}

    def execute(self, context):
        scene = context.scene
<<<<<<< HEAD
        settings = scene.better_baker_settings
=======
        wm = context.window_manager
>>>>>>> c5e196d721033f9de01f0df524ad775c0903720b
        
        if not scene.better_baker_textures:
            self.report({'WARNING'}, "Your texture baking list is empty!")
            return {'CANCELLED'}
<<<<<<< HEAD

        self._queue = [item for item in scene.better_baker_textures]
        self._total_maps = len(self._queue)

        self._timer = context.window_manager.event_timer_add(0.1, window=context.window)
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def cancel(self, context):
        if self._timer:
            context.window_manager.event_timer_remove(self._timer)
        return {'CANCELLED'}
    
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

        layout.active = True

        # Isolate configurable options into an active toggle matrix
        col_settings = layout.column()
        
        col_settings.label(text="Texture Size:")
        row = col_settings.row(align=True)
        row.prop(settings, "texture_size", expand=True)

        if settings.texture_size == 'CUSTOM':
            box = col_settings.box()
            col_px = box.column(align=True)
            col_px.prop(settings, "custom_width", text="Width (px)")
            col_px.prop(settings, "custom_height", text="Height (px)")

        col_settings.separator()
        col_settings.prop(settings, "prefix")
        col_settings.separator()

        col_settings.label(text="Textures:")
        row_list = col_settings.row()
        row_list.template_list("BAKER_UL_texture_list", "", scene, "better_baker_textures", scene, "better_baker_idx")
        
        col_btns = row_list.column(align=True)
        col_btns.menu("BAKER_MT_texture_select_menu", icon='ADD', text="")
        col_btns.operator("better_baker.remove_texture", icon='REMOVE', text="")

        layout.separator(factor=1)

        # Render execution zone
        col_render = layout.column()
        col_render.scale_y = 1.5
        col_render.operator("better_baker.render_bake", text="Render", icon='RENDER_STILL')
=======
            
        self.images_to_show = []
        self.current_index = 0
        self.total_maps = len(scene.better_baker_textures)
        
        wm.progress_begin(0, self.total_maps)
        context.window.cursor_set("WAIT")
        
        # Micro loop ticks every 0.1 seconds to yield GUI processing frames
        self._timer = wm.event_timer_add(0.1, window=context.window)
        wm.modal_handler_add(self)
        
        return {'RUNNING_MODAL'}
>>>>>>> c5e196d721033f9de01f0df524ad775c0903720b


# --- MENU: TEXTURE DROPDOWN LIST OPTION SELECTION ---
class BAKER_MT_texture_select_menu(bpy.types.Menu):
    """The dropdown selection box to populate the queue list"""
    bl_label = "Select Texture Map"
    bl_idname = "BAKER_MT_texture_select_menu"

    def draw(self, context):
        layout = self.layout
        
        # Mapping names cleanly to match Principled BSDF exactly
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
<<<<<<< HEAD
        
        # Highly requested extras that work perfectly with your engine layout:
        layout.operator("better_baker.add_texture", text="Specular IOR Level").texture_type = "Specular IOR Level"
        layout.operator("better_baker.add_texture", text="Alpha").texture_type = "Alpha"
=======
        layout.operator("better_baker.add_texture", text="Specular IOR Level").texture_type = "Specular IOR Level"
        layout.operator("better_baker.add_texture", text="Alpha").texture_type = "Alpha"

>>>>>>> c5e196d721033f9de01f0df524ad775c0903720b

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