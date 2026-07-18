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
        name="Prefix", default="tex_"
    )
    
    single_material_target: bpy.props.PointerProperty(
        name="Target Material",
        type=bpy.types.Material,
        description="The material whose node tree you want to bake"
    )


class BetterBakerTextureItem(bpy.types.PropertyGroup):
    name: bpy.props.StringProperty(name="Texture Type")

def spawn_image_viewer(context, image):
    """Safely spawns a new window and forces it to become an Image Editor."""
    if not image:
        return
        
    bpy.ops.wm.window_new()
    # Grab the newly created window
    new_win = context.window_manager.windows[-1]
    
    # Iterate through the areas of the new window
    for area in new_win.screen.areas:
        if area.type in {'VIEW_3D', 'EMPTY', 'IMAGE_EDITOR'}:
            area.type = 'IMAGE_EDITOR'
            # Access the space directly via the specific area space type
            for space in area.spaces:
                if space.type == 'IMAGE_EDITOR':
                    space.image = image
                    break
            break

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
    """Execute the baking process asynchronously with real-time UI updates"""
    bl_idname = "better_baker.render_bake"
    bl_label = "Bake Selected"
    
    _timer = None
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
                    spawn_image_viewer(context, bake_image)

            except Exception as e:
                self.report({'ERROR'}, f"Baking run encountered an error: {str(e)}")
                return self.cancel(context)

        return {'RUNNING_MODAL'}

    def execute(self, context):
        scene = context.scene
        settings = scene.better_baker_settings
        
        if not scene.better_baker_textures:
            self.report({'WARNING'}, "Your texture baking list is empty!")
            return {'CANCELLED'}
        
        if not bpy.context.selected_objects:
            self.report({'WARNING'}, "Select mesh objects to bake!")
            return {'CANCELLED'}

        self._queue = [item for item in scene.better_baker_textures]
        self._total_maps = len(self._queue)

        self._timer = context.window_manager.event_timer_add(0.1, window=context.window)
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def cancel(self, context):
        if self._timer:
            context.window_manager.event_timer_remove(self._timer)
        return {'CANCELLED'}

class BAKER_OT_bake_single_material(bpy.types.Operator):
    """Create a temporary flat plane, assign the material, and run the pre-existing bake function"""
    bl_idname = "better_baker.single_material_bake"
    bl_label = "Bake Single Material"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        scene = context.scene
        settings = scene.better_baker_settings
        
        if not settings.single_material_target:
            self.report({'WARNING'}, "Please select a material first!")
            return {'CANCELLED'}

        if not scene.better_baker_textures:
            self.report({'WARNING'}, "Your texture baking list is empty!")
            return {'CANCELLED'}

        mat = settings.single_material_target

        bpy.ops.object.select_all(action='DESELECT')
        bpy.ops.mesh.primitive_plane_add(size=2, enter_editmode=False, align='WORLD')
        plane_obj = context.active_object
        plane_obj.name = f"BakePlane_{mat.name}"

        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.uv.unwrap(method='ANGLE_BASED', margin=0.001)
        bpy.ops.object.mode_set(mode='OBJECT')

        if len(plane_obj.data.materials) == 0:
            plane_obj.data.materials.append(mat)
        else:
            plane_obj.data.materials[0] = mat

        plane_obj.select_set(True)
        context.view_layer.objects.active = plane_obj

        try:
            # Run the bake on the created plane using the regular bake viewer flow
            for texture_item in scene.better_baker_textures:
                bake_image = betterbakerengine(
                    [texture_item],
                    settings.texture_size,
                    settings,
                    settings.prefix,
                    objects=[plane_obj]
                )

                if bake_image:
                    spawn_image_viewer(context, bake_image)
        finally:
            # Clean up the temporary plane after baking
            bpy.ops.object.select_all(action='DESELECT')
            plane_obj.select_set(True)
            context.view_layer.objects.active = plane_obj
            bpy.ops.object.delete()

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

        # Avoid modifying ID datablocks during UI draw (not allowed).
        # Default textures are initialized when operators run instead.
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
        
        # Regular layout bake button
        col_render = layout.column()
        col_render.scale_y = 1.5
        
        # The regular button doesn't set the flag, so it defaults to False safely
        col_render.operator("better_baker.render_bake", text="Render", icon='RENDER_STILL')

        layout.separator()
        box_single = layout.box()
        box_single.label(text="Bake Single Material", icon='MATERIAL')
        box_single.prop(settings, "single_material_target", text="")
        box_single.operator("better_baker.single_material_bake", text="Bake Single Material", icon='PLAY')
        layout.separator(factor=1)

# --- 5. HELPER MENUS ---
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
        
        # Highly requested extras that work perfectly with your engine layout:
        layout.operator("better_baker.add_texture", text="Specular IOR Level").texture_type = "Specular IOR Level"
        layout.operator("better_baker.add_texture", text="Alpha").texture_type = "Alpha"

# --- 6. REGISTER REGION ---
preview_collections = {}
classes = (
    BetterBakerSettings,
    BetterBakerTextureItem,
    BAKER_OT_add_texture_type,
    BAKER_OT_remove_texture_type,
    BAKER_OT_render_bake,
    BAKER_OT_bake_single_material,
    BAKER_UL_texture_list,
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