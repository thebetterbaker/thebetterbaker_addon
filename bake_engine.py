import bpy

def bake_single_map(texture_item, resolution_mode, settings, prefix, objects=None):
    scene = bpy.context.scene
    scene.render.engine = 'CYCLES'
    
    # Set bake margin to prevent texture bleeding
    bake_margin = getattr(settings, 'bake_margin', 0)
    scene.render.bake.margin = bake_margin
    
    # Calculate separate independent dimension parameters
    if resolution_mode == '1K': res_w, res_h = 1024, 1024
    elif resolution_mode == '2K': res_w, res_h = 2048, 2048
    elif resolution_mode == '4K': res_w, res_h = 4096, 4096
    elif resolution_mode == '8K': res_w, res_h = 8192, 8192
    elif resolution_mode == 'CUSTOM': 
        res_w = settings.custom_width
        res_h = settings.custom_height
    else: 
        res_w, res_h = 2048, 2048

    if objects is None:
        obj = bpy.context.active_object
        objects = [obj] if (obj and obj.type == 'MESH') else []
    
    if not objects or not any(o.type == 'MESH' for o in objects):
        return None

    ui_name = texture_item.name  
    image_name = f"{prefix}_{ui_name.replace(' ', '_')}"
    
    if image_name in bpy.data.images:
        bake_image = bpy.data.images[image_name]
        bake_image.scale(res_w, res_h)
    else:
        bake_image = bpy.data.images.new(image_name, width=res_w, height=res_h)
    
    # Set proper non-color channel designations
    non_color_maps = {"Normal", "Roughness", "Metallic", "Clearcoat Weight", 
                      "Clearcoat Roughness", "Transmission Weight", "Subsurface Weight", 
                      "Specular IOR Level", "Alpha"}
    
    if ui_name in non_color_maps:
        bake_image.colorspace_settings.name = 'Non-Color'
    else:
        bake_image.colorspace_settings.name = 'sRGB'
        
    # --- FIX: Define mat_data HERE (Outside and completely before the try block) ---
    mat_data = {}

    socket_mapping = {
        "Base Color": "Base Color",
        "Roughness": "Roughness",
        "Metallic": "Metallic",
        "Clearcoat Weight": "Coat Weight",
        "Clearcoat Roughness": "Coat Roughness",
        "Emission Color": "Emission Color",
        "Emission Strength": "Emission Strength",
        "Transmission Weight": "Transmission Weight",
        "Subsurface Weight": "Subsurface Weight",
        "Specular IOR Level": "Specular IOR Level",
        "Alpha": "Alpha"
    }

    target_socket_name = socket_mapping.get(ui_name, ui_name)

    try:
        # --- CONDITION A: STANDARD CHANNELS VIA EMISSION ---
        if ui_name != "Normal":
            scene.render.bake.use_pass_direct = False
            scene.render.bake.use_pass_indirect = False
            scene.render.bake.use_pass_color = True
            bake_type_to_use = 'EMIT'

            for obj in objects:
                for slot in obj.material_slots:
                    mat = slot.material
                    if not mat or not mat.use_nodes: continue
                        
                    nodes = mat.node_tree.nodes
                    links = mat.node_tree.links
                    principled = next((n for n in nodes if n.type == 'BSDF_PRINCIPLED'), None)
                    if not principled: continue

                    node_emit = nodes.new(type='ShaderNodeEmission')
                    node_tex = nodes.new(type='ShaderNodeTexImage')
                    node_tex.image = bake_image
                    nodes.active = node_tex
                    
                    node_output = next((n for n in nodes if n.type == 'OUTPUT_MATERIAL'), None)
                    if not node_output: continue

                    orig_link = node_output.inputs['Surface'].links[0].from_socket if node_output.inputs['Surface'].is_linked else None
                    mat_data[mat.name] = (orig_link, node_emit, node_tex)
                    
                    target_socket = principled.inputs.get(target_socket_name)
                    if target_socket:
                        if target_socket.is_linked:
                            links.new(target_socket.links[0].from_socket, node_emit.inputs['Color'])
                        else:
                            val = target_socket.default_value
                            if isinstance(val, (int, float)):
                                node_emit.inputs['Color'].default_value = (val, val, val, 1.0)
                            else:
                                node_emit.inputs['Color'].default_value = (val[0], val[1], val[2], 1.0)
                        
                        node_emit.inputs['Strength'].default_value = 1.0
                        links.new(node_emit.outputs['Emission'], node_output.inputs['Surface'])

        # --- CONDITION B: NATIVE NORMALS ---
        else:
            bake_type_to_use = 'NORMAL'
            scene.render.bake.normal_space = 'TANGENT'

            for obj in objects:
                for slot in obj.material_slots:
                    mat = slot.material
                    if not mat or not mat.use_nodes: continue
                    nodes = mat.node_tree.nodes
                    
                    node_tex = nodes.new(type='ShaderNodeTexImage')
                    node_tex.image = bake_image
                    nodes.active = node_tex
                    mat_data[mat.name] = (None, None, node_tex)

        # Ensure all objects have UV layers
        for obj in objects:
            if obj.data.uv_layers and not obj.data.uv_layers.active:
                obj.data.uv_layers.active = obj.data.uv_layers[0]
        
        # Set first object as active for baking
        bpy.context.view_layer.objects.active = objects[0]
        
        bpy.ops.object.bake(type=bake_type_to_use, save_mode='INTERNAL')

    finally:
        # Revert network graphs cleanly
        for mat_name, (orig_link, temp_emit, temp_tex) in mat_data.items():
            m = bpy.data.materials.get(mat_name)
            if not m: continue
            if temp_emit:
                out = next((n for n in m.node_tree.nodes if n.type == 'OUTPUT_MATERIAL'), None)
                if orig_link and out:
                    m.node_tree.links.new(orig_link, out.inputs['Surface'])
                try: m.node_tree.nodes.remove(temp_emit)
                except ReferenceError: pass
            if temp_tex:
                try: m.node_tree.nodes.remove(temp_tex)
                except ReferenceError: pass

    return bake_image

def betterbakerengine(textures_list, resolution_mode, settings, prefix):
    """Entrypoint used by the addon to bake texture items for all selected objects together."""
    if not textures_list:
        return None

    # Get all selected mesh objects
    selected_objects = [obj for obj in bpy.context.selected_objects if obj.type == 'MESH']
    if not selected_objects:
        return None

    results = []
    for texture_item in textures_list:
        result = bake_single_map(texture_item, resolution_mode, settings, prefix, objects=selected_objects)
        if result:
            results.append(result)
    
    # Returns the last generated image data, or all if multiple textures baked
    return results[-1] if results else None