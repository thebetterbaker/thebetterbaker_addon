import bpy

def betterbakerengine(textures_list, resolution_mode, settings, prefix):
    scene = bpy.context.scene
    scene.render.engine = 'CYCLES'
    
    # 1. CONVERT RESOLUTION STRING TO INTEGER PIXELS
    if resolution_mode == '1K': res = 1024
    elif resolution_mode == '2K': res = 2048
    elif resolution_mode == '4K': res = 4096
    elif resolution_mode == '8K': res = 8192
    elif resolution_mode == 'CUSTOM':
        res = settings.custom_width # Safely grab custom inputs
    else:
        res = 2048

    # 2. VALIDATE THE SELECTION
    obj = bpy.context.active_object
    if not obj or obj.type != 'MESH':
        print("Error: No Mesh selected")
        return False

    # Force Bake settings to be clean
    scene.render.bake.use_pass_direct = False
    scene.render.bake.use_pass_indirect = False
    scene.render.bake.use_pass_color = True

    # 3. THE LOOP: Iterate through each map type the user requested
    for texture_item in textures_list:
        # Match names to Blender's Principled BSDF input sockets
        ui_name = texture_item.name  # e.g., "Base Color" or "Roughness"
        
        image_name = f"{prefix}_{ui_name.replace(' ', '_')}"
        if image_name in bpy.data.images:
            bake_image = bpy.data.images[image_name]
            bake_image.scale(res, res)
        else:
            bake_image = bpy.data.images.new(image_name, width=res, height=res)
        
        mat_data = {}

        for slot in obj.material_slots:
            mat = slot.material
            if not mat or not mat.use_nodes: continue
                
            nodes = mat.node_tree.nodes
            links = mat.node_tree.links
            
            principled = next((n for n in nodes if n.type == 'BSDF_PRINCIPLED'), None)
            if not principled:
                print(f"Skipping {mat.name}: No Principled BSDF found.")
                continue

            # Setup Temp Nodes
            node_emit = nodes.new(type='ShaderNodeEmission')
            node_tex = nodes.new(type='ShaderNodeTexImage')
            node_tex.image = bake_image
            nodes.active = node_tex
            
            node_output = next((n for n in nodes if n.type == 'OUTPUT_MATERIAL'), None)
            if not node_output: continue

            # Save state
            orig_link = node_output.inputs['Surface'].links[0].from_socket if node_output.inputs['Surface'].is_linked else None
            mat_data[mat.name] = (orig_link, node_emit, node_tex)
            
            # Route socket value to Emission node
            target_socket = principled.inputs.get(ui_name)
            
            if target_socket:
                if target_socket.is_linked:
                    links.new(target_socket.links[0].from_socket, node_emit.inputs['Color'])
                else:
                    val = target_socket.default_value
                    if isinstance(val, (int, float)):
                        node_emit.inputs['Color'].default_value = (val, val, val, 1.0)
                    else: # It's an RGBA vector color
                        node_emit.inputs['Color'].default_value = (val[0], val[1], val[2], 1.0)
                
                node_emit.inputs['Strength'].default_value = 1.0
                links.new(node_emit.outputs['Emission'], node_output.inputs['Surface'])

        # BAKE active channel pass
        # 4. BAKE
        if obj.data.uv_layers:
            # If no layer is active, default to the first one available
            if not obj.data.uv_layers.active:
                obj.data.uv_layers.active = obj.data.uv_layers[0]
            
        print(f"Baking {ui_name}...") # Changed parameter_name to ui_name to match our loop
        bpy.ops.object.bake(type='EMIT', save_mode='INTERNAL')

        # RESTORE materials graph for this specific channel pass
        for mat_name, (orig_link, temp_emit, temp_tex) in mat_data.items():
            m = bpy.data.materials.get(mat_name)
            if not m: continue
            out = next((n for n in m.node_tree.nodes if n.type == 'OUTPUT_MATERIAL'), None)
            if orig_link and out:
                m.node_tree.links.new(orig_link, out.inputs['Surface'])
            m.node_tree.nodes.remove(temp_emit)
            # Keeping temp_tex commented out keeps it inside the material tree safely!

    print("Bake Finished.")
    return True