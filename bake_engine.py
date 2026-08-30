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
        # print(f"mix shader node - src 1 : {src1}")
        # print(f"mix shader node - src 2 : {src2}")
        # Connect Slot 1 data to our new Mix Color node
        if isinstance(src1, bpy.types.NodeSocket):
            if src1.is_output:
                tree.links.new(src1, mix_node.inputs[input1_name])
                # print("linked as output")
            elif src1.is_linked:
                tree.links.new(src1.links[0].from_socket, mix_node.inputs[input1_name])
                # print("linked as link")
            else:
                val = src1.default_value
                mix_node.inputs[input1_name].default_value = val if hasattr(val, '__len__') and len(val) == 4 else (val, val, val, 1.0)

        # Connect Slot 2 data to our new Mix Color node
        if isinstance(src2, bpy.types.NodeSocket):
            if src2.is_output:
                tree.links.new(src2, mix_node.inputs[input2_name])
                # print("linked as output")
            elif src2.is_linked:
                tree.links.new(src2.links[0].from_socket, mix_node.inputs[input2_name])
                # print("linked as link")
            else:
                # print("linked as fail")
                val = src2.default_value
                mix_node.inputs[input2_name].default_value = val if hasattr(val, '__len__') and len(val) == 4 else (val, val, val, 1.0)

        # print(f"------attepting to return {mix_node.outputs[0]}")
        color_output = next((o for o in mix_node.outputs if o.type == 'RGBA'), None)
        return color_output if color_output else mix_node.outputs[0]
    

    # Case 3: Standalone basic shaders -> Dive into their Color property
    elif from_node.bl_idname in {'ShaderNodeBsdfDiffuse', 'ShaderNodeBsdfGlossy', 'ShaderNodeBsdfEmission'}:
        color_socket = from_node.inputs.get('Color')
        if color_socket:
            return trace_channel_source(color_socket, target_channel, tree)
        return from_socket
    
    return from_socket

def get_used_udim_tiles(objects):
    """Scans each object's active UV layer and returns the sorted list of
    UDIM tile numbers (1001, 1002, ...) touched by any UV coordinate.
    Falls back to [1001] if nothing is found, so callers always get a usable list."""
    tiles = set()
    for obj in objects:
        if obj.type != 'MESH' or not obj.data.uv_layers.active:
            continue
        for uv in obj.data.uv_layers.active.data:
            u, v = uv.uv
            tile_u = int(u) if u >= 0 else int(u) - 1
            tile_v = int(v) if v >= 0 else int(v) - 1
            tiles.add(1001 + tile_u + tile_v * 10)
    return sorted(tiles) if tiles else [1001]

def bake_single_map(texture_item, resolution_mode, settings, prefix, objects=None):
    scene = bpy.context.scene
    scene.render.engine = 'CYCLES'
    
    # Set bake margin to prevent texture bleeding
    bake_margin = getattr(settings, 'bake_margin', 0)
    scene.render.bake.margin = bake_margin
    scene.render.use_persistent_data = False
    
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
    
    use_udims = getattr(settings, 'use_udims', False)

    if use_udims:
        # --- UDIM PATH (contained): creates/updates a tiled image instead ---
        udim_tiles = get_used_udim_tiles(objects)

        bake_image = bpy.data.images.get(image_name)
        if bake_image and bake_image.source != 'TILED':
            # A non-tiled image exists with this name from a prior non-UDIM bake — replace it
            bpy.data.images.remove(bake_image)
            bake_image = None

        if bake_image is None:
            bake_image = bpy.data.images.new(image_name, width=res_w, height=res_h, tiled=True)

        existing_tile_numbers = {t.number for t in bake_image.tiles}

        for tile_number in udim_tiles:
            if tile_number not in existing_tile_numbers:
                bake_image.tiles.new(tile_number=tile_number)
        for tile in bake_image.tiles:
            if tile.number in udim_tiles:
                bake_image.tiles.active = tile
                with bpy.context.temp_override(edit_image=bake_image):
                    bpy.ops.image.tile_fill(
                        color=(0.0, 0.0, 0.0, 1.0),
                        width=res_w,
                        height=res_h,
                    )
        bake_image.update()
    else:
        if image_name in bpy.data.images:
            bake_image = bpy.data.images[image_name]
            try:
                current_size = (bake_image.size[0], bake_image.size[1])
            except Exception:
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
            # print(f"--- Starting Bake for Channel: {ui_name} ---")
            scene.render.bake.use_clear = False
            scene.render.bake.use_pass_direct = False
            scene.render.bake.use_pass_indirect = False
            scene.render.bake.use_pass_color = True
            bake_type_to_use = 'EMIT'

            non_color_channels = {
                "Roughness", "Metallic", "Clearcoat Weight", "Clearcoat Roughness", 
                "Emission Strength", "Transmission Weight", "Subsurface Weight", 
                "Specular IOR Level", "Alpha"
            }

            if ui_name in non_color_channels:
                initial_pixels = [0.5, 0.5, 0.5, 1.0] * (res_w * res_h)
                if use_udims:
                    for tile in bake_image.tiles:
                        bake_image.tiles.active = tile
                        bake_image.pixels.foreach_set(initial_pixels)
                else:
                    bake_image.pixels.foreach_set(initial_pixels)
                bake_image.update()
            else:
                scene.render.bake.use_clear = True

            for obj in objects:
                # print(f"Checking Object: {obj.name}")
                for slot in obj.material_slots:
                    mat = slot.material
                    # if not mat: 
                    #     print(f"  Skipped: Slot is empty")
                    #     continue
                    # if not mat.use_nodes: 
                    #     print(f"  Skipped: Material '{mat.name}' does not use nodes")
                    #     continue
                        
                    nodes = mat.node_tree.nodes
                    links = mat.node_tree.links
                    
                    node_output = next((n for n in nodes if n.type == 'OUTPUT_MATERIAL'), None)
                    # if not node_output:
                    #     print(f"  Skipped: Material '{mat.name}' has no Output node")
                    #     continue
                    # if not node_output.inputs['Surface'].is_linked: 
                    #     print(f"  Skipped: Material '{mat.name}' Output Surface is not linked")
                    #     continue

                    # print(f"  Processing Material: {mat.name}")

                    # Create bake elements
                    node_emit = nodes.new(type='ShaderNodeEmission')
                    node_tex = nodes.new(type='ShaderNodeTexImage')
                    node_tex.image = bake_image
                    nodes.active = node_tex
                    # print(f"    Created temporary nodes successfully!")
                    
                    # Store data for cleanup later
                    orig_link = node_output.inputs['Surface'].links[0].from_socket
                    mat_data[mat.name] = (orig_link, node_emit, node_tex)
                    
                    # Trace back from Output Node to find our targeted source data
                    # Trace back from Output Node to find our targeted source data
                    nodes.active = node_tex
                    final_source = trace_channel_source(node_output.inputs['Surface'], target_socket_name, mat.node_tree)
                    # print(f"    Traced back to source: {final_source}")

                    # for node in mat.node_tree.nodes:
                    #     if "TEMP_BAKE_MIX" in node.name:
                    #         print(f"TEMP_BAKE_MIX found: {node.name}")
                    #         for inp in node.inputs:
                    #             print(f"  Input '{inp.name}': is_linked={inp.is_linked}, default={getattr(inp, 'default_value', 'N/A')}")
                    #         for out in node.outputs:
                    #             print(f"  Output '{out.name}': is_linked={out.is_linked}")
                    if final_source:
                        print(f"    Processing final_source: {final_source} (Node: {final_source.node.bl_idname if hasattr(final_source, 'node') else 'None'})")
                        
                        # CASE 1: It's an output socket (The temporary Mix node output from your recursion)
                        if hasattr(final_source, 'is_output') and final_source.is_output:
                            mat.node_tree.links.new(final_source, node_emit.inputs['Color'])
                            # print("    [LINKED] Output socket directly to Emission Color.")
                            
                        # CASE 2: It's an input socket that has an active wire connection
                        elif hasattr(final_source, 'is_linked') and final_source.is_linked:
                            mat.node_tree.links.new(final_source.links[0].from_socket, node_emit.inputs['Color'])
                            # print(f"    [LINKED] Upstream socket {final_source.links[0].from_socket} to Emission Color.")
                            
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
            normal_color = (0.5, 0.5, 1.0, 1.0)
            if use_udims:
                flat = normal_color * (res_w * res_h)
                for tile in bake_image.tiles:
                    bake_image.tiles.active = tile
                    bake_image.pixels.foreach_set(flat)
            else:
                bake_image.pixels.foreach_set(normal_color * (res_w * res_h))

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
        bake_image.gl_free()

    finally:
        for mat_name, (orig_link, temp_emit, temp_tex) in mat_data.items():
            m = bpy.data.materials.get(mat_name)
            if not m: continue
            
            # Restore the original surface connection if it was replaced
            if temp_emit and orig_link:
                out = next((n for n in m.node_tree.nodes if n.type == 'OUTPUT_MATERIAL'), None)
                if out:
                    m.node_tree.links.new(orig_link, out.inputs['Surface'])

            # Remove temporary bake nodes created for this material
            for temp_node in (temp_emit, temp_tex):
                if temp_node and temp_node.name in m.node_tree.nodes:
                    try:
                        m.node_tree.nodes.remove(temp_node)
                    except Exception:
                        pass

            # Clean up any TEMP_BAKE_MIX nodes left by trace_channel_source
            for node in list(m.node_tree.nodes):
                if node.name == "TEMP_BAKE_MIX":
                    m.node_tree.nodes.remove(node)

    return bake_image

def betterbakerengine(textures_list, resolution_mode, settings, prefix, objects=None):
    """Entrypoint used by the addon to bake texture items for all selected objects together."""
    if not textures_list:
        return None

    if objects is None:
        objects = [obj for obj in bpy.context.selected_objects if obj.type == 'MESH']
    if not objects:
        return None

    results = []
    for texture_item in textures_list:
        result = bake_single_map(texture_item, resolution_mode, settings, prefix, objects=objects)
        if result:
            results.append(result)
    
    # Returns the last generated image data, or all if multiple textures baked
    return results[-1] if results else None