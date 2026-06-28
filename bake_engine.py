import bpy

def trace_channel_source(socket, target_channel, tree):
    """Recursively traces nodes backward, pulling data from specific channels 
    even when hidden behind Mix Shaders."""
    if not socket:
        return None

    # Catch unlinked sockets immediately so they don't break the recursive chain
    if not socket.is_linked:
        return socket

    from_node = socket.links[0].from_node
    from_socket = socket.links[0].from_socket

    # Case 1: Standard Principled BSDF -> Dive into the targeted channel input
    if from_node.bl_idname == 'ShaderNodeBsdfPrincipled':
        mapped_socket = from_node.inputs.get(target_channel)
        if mapped_socket:
            return trace_channel_source(mapped_socket, target_channel, tree)
        return from_socket

    # Case 2: Mix Shader -> Intercept the shaders and grab their matching target channels
    elif from_node.bl_idname == 'ShaderNodeMixShader':
        try:
            mix_node = tree.nodes.new(type='ShaderNodeMix')
            mix_node.data_type = 'RGBA'
            input1_name, input2_name, fac_name = 'A', 'B', 'Factor'
        except:
            mix_node = tree.nodes.new(type='ShaderNodeMixRGB')
            mix_node.blend_type = 'MIX'
            input1_name, input2_name, fac_name = 'Color1', 'Color2', 'Fac'
        mix_node.name = "TEMP_BAKE_MIX"
        tree.nodes.active = mix_node # Force Blender to update the context focus to this node
        # Link the Factor map or value
        fac_input = from_node.inputs['Fac']
        if fac_input.is_linked:
            tree.links.new(fac_input.links[0].from_socket, mix_node.inputs[fac_name])
        else:
            mix_node.inputs[fac_name].default_value = fac_input.default_value

        # RECURSION: Pass the shader slots directly back into the pipeline
        src1 = trace_channel_source(from_node.inputs[1], target_channel, tree)
        src2 = trace_channel_source(from_node.inputs[2], target_channel, tree)
        print(f"mix shader node - src 1 : {src1}")
        print(f"mix shader node - src 2 : {src2}")
        # Connect Slot 1 data to our new Mix Color node
        if isinstance(src1, bpy.types.NodeSocket):
            if src1.is_output:
                tree.links.new(src1, mix_node.inputs[input1_name])
                print("linked as output")
            elif src1.is_linked:
                tree.links.new(src1.links[0].from_socket, mix_node.inputs[input1_name])
                print("linked as link")
            else:
                val = src1.default_value
                mix_node.inputs[input1_name].default_value = val if hasattr(val, '__len__') and len(val) == 4 else (val, val, val, 1.0)

        # Connect Slot 2 data to our new Mix Color node
        if isinstance(src2, bpy.types.NodeSocket):
            if src2.is_output:
                tree.links.new(src2, mix_node.inputs[input2_name])
                print("linked as output")
            elif src2.is_linked:
                tree.links.new(src2.links[0].from_socket, mix_node.inputs[input2_name])
                print("linked as link")
            else:
                print("linked as fail")
                val = src2.default_value
                mix_node.inputs[input2_name].default_value = val if hasattr(val, '__len__') and len(val) == 4 else (val, val, val, 1.0)

        print(f"------attepting to return {mix_node.outputs[0]}")
        color_output = next((o for o in mix_node.outputs if o.type == 'RGBA'), None)
        return color_output if color_output else mix_node.outputs[0]
    

    # Case 3: Standalone basic shaders -> Dive into their Color property
    elif from_node.bl_idname in {'ShaderNodeBsdfDiffuse', 'ShaderNodeBsdfGlossy', 'ShaderNodeBsdfEmission'}:
        color_socket = from_node.inputs.get('Color')
        if color_socket:
            return trace_channel_source(color_socket, target_channel, tree)
        return from_socket
    
    return from_socket

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
        # Ensure the existing image matches the requested size. Some Blender
        # image scale operations don't reliably resize baked-images in all
        # contexts, which can leave old (e.g. 4K) images active. If the sizes
        # differ, remove and recreate the image to guarantee correct resolution.
        try:
            current_size = (bake_image.size[0], bake_image.size[1])
        except Exception:
            # Fallback in case the image API differs; try width/height attrs
            try:
                current_size = (bake_image.size[0], bake_image.size[1])
            except Exception:
                current_size = None

        if current_size is None or current_size != (res_w, res_h):
            try:
                bpy.data.images.remove(bake_image)
            except Exception:
                pass
            bake_image = bpy.data.images.new(image_name, width=res_w, height=res_h)
        else:
            # image already matches requested size; keep it
            pass
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
            print(f"--- Starting Bake for Channel: {ui_name} ---")
            scene.render.bake.use_pass_direct = False
            scene.render.bake.use_pass_indirect = False
            scene.render.bake.use_pass_color = True
            bake_type_to_use = 'EMIT'

            for obj in objects:
                print(f"Checking Object: {obj.name}")
                for slot in obj.material_slots:
                    mat = slot.material
                    if not mat: 
                        print(f"  Skipped: Slot is empty")
                        continue
                    if not mat.use_nodes: 
                        print(f"  Skipped: Material '{mat.name}' does not use nodes")
                        continue
                        
                    nodes = mat.node_tree.nodes
                    links = mat.node_tree.links
                    
                    node_output = next((n for n in nodes if n.type == 'OUTPUT_MATERIAL'), None)
                    if not node_output:
                        print(f"  Skipped: Material '{mat.name}' has no Output node")
                        continue
                    if not node_output.inputs['Surface'].is_linked: 
                        print(f"  Skipped: Material '{mat.name}' Output Surface is not linked")
                        continue

                    print(f"  Processing Material: {mat.name}")

                    # Create bake elements
                    node_emit = nodes.new(type='ShaderNodeEmission')
                    node_tex = nodes.new(type='ShaderNodeTexImage')
                    node_tex.image = bake_image
                    nodes.active = node_tex
                    print(f"    Created temporary nodes successfully!")
                    
                    # Store data for cleanup later
                    orig_link = node_output.inputs['Surface'].links[0].from_socket
                    mat_data[mat.name] = (orig_link, node_emit, node_tex)
                    
                    # Trace back from Output Node to find our targeted source data
                    # Trace back from Output Node to find our targeted source data
                    nodes.active = node_tex
                    final_source = trace_channel_source(node_output.inputs['Surface'], target_socket_name, mat.node_tree)
                    print(f"    Traced back to source: {final_source}")

                    for node in mat.node_tree.nodes:
                        if "TEMP_BAKE_MIX" in node.name:
                            print(f"TEMP_BAKE_MIX found: {node.name}")
                            for inp in node.inputs:
                                print(f"  Input '{inp.name}': is_linked={inp.is_linked}, default={getattr(inp, 'default_value', 'N/A')}")
                            for out in node.outputs:
                                print(f"  Output '{out.name}': is_linked={out.is_linked}")
                    if final_source:
                        print(f"    Processing final_source: {final_source} (Node: {final_source.node.bl_idname if hasattr(final_source, 'node') else 'None'})")
                        
                        # CASE 1: It's an output socket (The temporary Mix node output from your recursion)
                        if hasattr(final_source, 'is_output') and final_source.is_output:
                            mat.node_tree.links.new(final_source, node_emit.inputs['Color'])
                            print("    [LINKED] Output socket directly to Emission Color.")
                            
                        # CASE 2: It's an input socket that has an active wire connection
                        elif hasattr(final_source, 'is_linked') and final_source.is_linked:
                            mat.node_tree.links.new(final_source.links[0].from_socket, node_emit.inputs['Color'])
                            print(f"    [LINKED] Upstream socket {final_source.links[0].from_socket} to Emission Color.")
                            
                        # CASE 3: It's an unlinked input socket with a default numeric/color value
                        elif hasattr(final_source, 'default_value'):
                            val = final_source.default_value
                            if isinstance(val, (int, float)):
                                node_emit.inputs['Color'].default_value = (val, val, val, 1.0)
                            else:
                                node_emit.inputs['Color'].default_value = (val[0], val[1], val[2], 1.0)
                            print(f"    [VALUE SET] Applied default value: {val}")
                            
                        # CASE 4: Absolute fallback if it's an untyped socket object passed directly
                        else:
                            try:
                                mat.node_tree.links.new(final_source, node_emit.inputs['Color'])
                                print("    [LINKED] Handled via absolute fallback.")
                            except Exception as e:
                                print(f"    [FAILED] Fallback failed to link: {e}")
                    else:
                        print("    [WARNING] final_source returned None!")
                                            
                    node_emit.inputs['Strength'].default_value = 1.0
                    link = mat.node_tree.links.new(node_emit.outputs['Emission'], node_output.inputs['Surface'])
                    print(f"Link created: {link}")
                    print(f"Surface now linked: {node_output.inputs['Surface'].is_linked}")
                    print(f"Surface linked to: {node_output.inputs['Surface'].links}")
                    print(f"    Nodes linked and ready to bake.")

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
        for mat_name, (orig_link, temp_emit, temp_tex) in mat_data.items():
            m = bpy.data.materials.get(mat_name)
            if not m: continue
            
            # Clean up any TEMP_BAKE_MIX nodes left by trace_channel_source
            for node in list(m.node_tree.nodes):
                if node.name == "TEMP_BAKE_MIX":
                    m.node_tree.nodes.remove(node)
            
            if temp_emit:
                out = next((n for n in m.node_tree.nodes if n.type == 'OUTPUT_MATERIAL'), None)
                if orig_link and out:
                    m.node_tree.links.new(orig_link, out.inputs['Surface'])

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