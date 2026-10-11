"""Reader for Accelergy v0.4 architecture files.

The Timeloop harness calls this module. Do not run it as a script.

The module reads the architecture file and makes a flat list of components.
It obeys the Timeloop/Accelergy v4 specification:

- Node tags: !Hierarchical, !Parallel, !Pipelined, !Component, !Container,
  !Nothing.
- Spatial fanout on Component, Container, and Nothing nodes.
- The sparse_optimizations, area_scale, energy_scale, and enabled fields.
"""

from pathlib import Path

import yaml
from collections import OrderedDict
from copy import deepcopy
from typing import Dict, List, Any, Tuple, Optional, Union

from npuwattch.diagnostics import info, warning


class TreeNode:
    """One node of the architecture hierarchy tree."""
    def __init__(self, name: str, node_type: str, comp_class: Optional[str] = None,
                 subclass: Optional[str] = None, spatial: Optional[Dict] = None,
                 attributes: Optional[Dict] = None, required_actions: Optional[List] = None,
                 constraints: Optional[Dict] = None, sparse_optimizations: Optional[Dict] = None,
                 area_scale: Optional[float] = None, energy_scale: Optional[float] = None,
                 enabled: bool = True, networks: Optional[List] = None):
        self.name = name
        # Node types: 'Hierarchical', 'Parallel', 'Pipelined', 'Container', 'Component', 'Nothing', 'Root'
        self.node_type = node_type
        self.comp_class = comp_class
        self.subclass = subclass
        self.spatial = spatial or {}
        self.attributes = attributes or {}
        self.required_actions = required_actions or []
        self.constraints = constraints
        self.sparse_optimizations = sparse_optimizations
        self.area_scale = area_scale
        self.energy_scale = energy_scale
        self.enabled = enabled
        self.networks = networks or []
        self.children: List['TreeNode'] = []
        self.parent: Optional['TreeNode'] = None
        
    def add_child(self, child: 'TreeNode'):
        """Add a child node to this node."""
        child.parent = self
        self.children.append(child)
        
    def get_hierarchical_path(self) -> str:
        """
        Return the full hierarchical path in dot notation.
        The path includes Container, Component, and Nothing nodes.
        The path does not include the branch nodes: Hierarchical, Parallel,
        Pipelined, and Root.
        """
        path_parts = []
        current = self
        
        while current is not None and current.node_type != 'Root':
            if current.node_type in ['Container', 'Component', 'Nothing']:
                path_parts.insert(0, current.name)
            # Ignore the branch nodes: Hierarchical, Parallel, Pipelined.
            current = current.parent
        
        return '.'.join(path_parts)
    
    def calculate_accumulated_mesh(self) -> Tuple[int, int]:
        """
        Return the accumulated mesh dimensions from the root to this node.
        The result is the product of the spatial dimensions of this node and
        of all its parent nodes.
        """
        meshX, meshY = 1, 1
        node = self
        while node is not None:
            # Multiply by the spatial dimensions of each Container, Component, or Nothing node.
            if node.spatial:
                meshX *= node.spatial.get('meshX', 1)
                meshY *= node.spatial.get('meshY', 1)
            node = node.parent
        return meshX, meshY
    
    def get_own_fanout(self) -> int:
        """Return the spatial fanout of this node only (meshX * meshY)."""
        if self.spatial:
            return self.spatial.get('meshX', 1) * self.spatial.get('meshY', 1)
        return 1
    
    def __repr__(self):
        return f"TreeNode({self.name}, {self.node_type})"


class AccelergyV04Flattener:
    """Reads an Accelergy v0.4 architecture file and makes a flat component list."""
    
    def __init__(self):
        self.flat_components: List[OrderedDict] = []
        self.tree_root: Optional[TreeNode] = None
        self.top_level_attributes: Dict = {}
        self.constraint_list: List[Dict] = []
        self.sparse_opt_list: List[Dict] = []
        
    def parse_yaml(self, filepath: str) -> Dict:
        """Read a YAML file that has the Accelergy node tags."""
        def container_constructor(loader, node):
            value = loader.construct_mapping(node, deep=True)
            value['_type'] = 'Container'
            return value
        
        def component_constructor(loader, node):
            value = loader.construct_mapping(node, deep=True)
            value['_type'] = 'Component'
            return value
        
        def parallel_constructor(loader, node):
            value = loader.construct_mapping(node, deep=True)
            value['_type'] = 'Parallel'
            return value
        
        def hierarchical_constructor(loader, node):
            value = loader.construct_mapping(node, deep=True)
            value['_type'] = 'Hierarchical'
            return value
        
        def pipelined_constructor(loader, node):
            value = loader.construct_mapping(node, deep=True)
            value['_type'] = 'Pipelined'
            return value
        
        def nothing_constructor(loader, node):
            value = loader.construct_mapping(node, deep=True)
            value['_type'] = 'Nothing'
            return value
        
        yaml.SafeLoader.add_constructor('!Container', container_constructor)
        yaml.SafeLoader.add_constructor('!Component', component_constructor)
        yaml.SafeLoader.add_constructor('!Parallel', parallel_constructor)
        yaml.SafeLoader.add_constructor('!Hierarchical', hierarchical_constructor)
        yaml.SafeLoader.add_constructor('!Pipelined', pipelined_constructor)
        yaml.SafeLoader.add_constructor('!Nothing', nothing_constructor)
        
        with open(filepath, 'r') as f:
            return yaml.safe_load(f)
    
    def interpret_component_list(self, name: str) -> Tuple[str, Optional[str], Optional[int]]:
        """Find the list notation ``[start..end]`` in a component name."""
        left_bracket_idx = name.find('[')
        range_flag = name.find('..')
        
        if left_bracket_idx == -1 or range_flag == -1:
            return name, None, None
        
        right_bracket_idx = name.find(']')
        if right_bracket_idx == -1:
            return name, None, None
        
        name_base = name[:left_bracket_idx]
        list_start_str = name[left_bracket_idx + 1:range_flag]
        list_end_str = name[range_flag + 2:right_bracket_idx]
        
        try:
            list_start_idx = int(list_start_str)
            list_end_idx = int(list_end_str)
            list_suffix = f"[{list_start_idx}..{list_end_idx}]"
            list_length = list_end_idx - list_start_idx + 1
            return name_base, list_suffix, list_length
        except ValueError:
            return name, None, None
    
    def build_hierarchy_tree(self, content: Dict) -> TreeNode:
        """Make the hierarchy tree from the YAML content."""
        arch = content.get('architecture', {})
        root = TreeNode('root', 'Root')
        
        if 'nodes' in arch:
            nodes = arch['nodes']
            
            # The first node is usually the top-level container.
            if nodes and nodes[0].get('_type') == 'Container':
                top_container = nodes[0]
                top_name = top_container.get('name', 'System')
                top_attrs = top_container.get('attributes', {})
                self.top_level_attributes = deepcopy(top_attrs)
                
                top_node = TreeNode(
                    name=f"{top_name}_top_level",
                    node_type='Container',
                    attributes=top_attrs,
                    spatial=top_container.get('spatial', {}),
                    constraints=top_container.get('constraints', None),
                    sparse_optimizations=top_container.get('sparse_optimizations', None),
                    networks=top_container.get('networks', [])
                )
                root.add_child(top_node)
                
                # Process the other nodes in hierarchical mode.
                self._process_hierarchical_nodes(nodes[1:], top_node)
            else:
                top_node = TreeNode('System_top_level', 'Container')
                root.add_child(top_node)
                self._process_hierarchical_nodes(nodes, top_node)
        
        return root
    
    def _process_hierarchical_nodes(self, nodes: List[Dict], parent: TreeNode):
        """
        Process the nodes in hierarchical mode.
        Each Container becomes the scope of the subsequent nodes.
        """
        scope_stack = [parent]
        
        for node in nodes:
            node_type = node.get('_type', 'Component')
            
            if node_type == 'Hierarchical':
                # Make a hierarchical branch node.
                hier_node = TreeNode(name='(hierarchical)', node_type='Hierarchical')
                scope_stack[-1].add_child(hier_node)
                
                # Process the children in hierarchical mode.
                if 'nodes' in node:
                    self._process_hierarchical_nodes(node['nodes'], hier_node)
            
            elif node_type == 'Parallel':
                # Make a parallel branch node.
                parallel_node = TreeNode(name='(parallel)', node_type='Parallel')
                scope_stack[-1].add_child(parallel_node)
                
                # Process the children. Each child is a sibling.
                if 'nodes' in node:
                    for child_node in node['nodes']:
                        self._process_node(child_node, parallel_node)
            
            elif node_type == 'Pipelined':
                # Make a pipelined branch node.
                pipelined_node = TreeNode(name='(pipelined)', node_type='Pipelined')
                scope_stack[-1].add_child(pipelined_node)
                
                # Process the children as for a parallel node.
                if 'nodes' in node:
                    for child_node in node['nodes']:
                        self._process_node(child_node, pipelined_node)
            
            elif node_type == 'Container':
                # Make the container. It becomes the current scope.
                container_node = self._create_container_node(node)
                scope_stack[-1].add_child(container_node)
                scope_stack.append(container_node)
            
            elif node_type == 'Component':
                # Make the component in the current scope.
                component_node = self._create_component_node(node)
                scope_stack[-1].add_child(component_node)
            
            elif node_type == 'Nothing':
                # Make the Nothing node with all its attributes.
                nothing_node = self._create_nothing_node(node)
                scope_stack[-1].add_child(nothing_node)
    
    def _process_node(self, node: Dict, parent: TreeNode):
        """Process one child of a Parallel, Pipelined, or nested Hierarchical node."""
        node_type = node.get('_type', 'Component')
        
        if node_type == 'Hierarchical':
            hier_node = TreeNode(name='(hierarchical)', node_type='Hierarchical')
            parent.add_child(hier_node)
            if 'nodes' in node:
                self._process_hierarchical_nodes(node['nodes'], hier_node)
        
        elif node_type == 'Parallel':
            parallel_node = TreeNode(name='(parallel)', node_type='Parallel')
            parent.add_child(parallel_node)
            if 'nodes' in node:
                for child_node in node['nodes']:
                    self._process_node(child_node, parallel_node)
        
        elif node_type == 'Pipelined':
            pipelined_node = TreeNode(name='(pipelined)', node_type='Pipelined')
            parent.add_child(pipelined_node)
            if 'nodes' in node:
                for child_node in node['nodes']:
                    self._process_node(child_node, pipelined_node)
        
        elif node_type == 'Container':
            container_node = self._create_container_node(node)
            parent.add_child(container_node)
        
        elif node_type == 'Component':
            component_node = self._create_component_node(node)
            parent.add_child(component_node)
        
        elif node_type == 'Nothing':
            nothing_node = self._create_nothing_node(node)
            parent.add_child(nothing_node)
    
    def _create_container_node(self, node: Dict) -> TreeNode:
        """Make a Container tree node."""
        return TreeNode(
            name=node.get('name', 'container'),
            node_type='Container',
            spatial=node.get('spatial', {}),
            attributes=node.get('attributes', {}),
            constraints=node.get('constraints', None),
            sparse_optimizations=node.get('sparse_optimizations', None),
            networks=node.get('networks', [])
        )
    
    def _create_component_node(self, node: Dict) -> TreeNode:
        """Make a Component tree node with all v4 attributes."""
        return TreeNode(
            name=node.get('name', 'component'),
            node_type='Component',
            comp_class=node.get('class', 'unknown'),
            subclass=node.get('subclass', None),
            spatial=node.get('spatial', {}),
            attributes=node.get('attributes', {}),
            required_actions=node.get('required_actions', None),
            constraints=node.get('constraints', None),
            sparse_optimizations=node.get('sparse_optimizations', None),
            area_scale=node.get('area_scale', None),
            energy_scale=node.get('energy_scale', None),
            enabled=node.get('enabled', True)
        )
    
    def _create_nothing_node(self, node: Dict) -> TreeNode:
        """Make a Nothing tree node with all v4 attributes."""
        return TreeNode(
            name=node.get('name', 'nothing'),
            node_type='Nothing',
            comp_class=node.get('class', 'nothing'),
            spatial=node.get('spatial', {}),
            attributes=node.get('attributes', {}),
            constraints=node.get('constraints', None),
            sparse_optimizations=node.get('sparse_optimizations', None),
            enabled=node.get('enabled', True)
        )
    
    def flatten_hierarchy(self, content: Dict) -> Dict:
        """Entry point: change the architecture hierarchy into a flat component list."""
        arch = content.get('architecture', {})
        version = arch.get('version', '0.4')
        
        # Reset the state.
        self.flat_components = []
        self.constraint_list = []
        self.sparse_opt_list = []
        
        # Make the hierarchy tree.
        self.tree_root = self.build_hierarchy_tree(content)
        
        # Make the flat component list from the tree.
        self._flatten_tree_node(self.tree_root, {})
        
        # Make the flat YAML structure.
        flattened = {
            'architecture': {
                'version': str(version),
                'local': self.flat_components
            }
        }
        
        # Add the constraints, if there are some.
        if self.constraint_list:
            flattened['architecture_constraints'] = {
                'targets': self.constraint_list
            }
        
        # Add the sparse optimizations, if there are some.
        if self.sparse_opt_list:
            flattened['sparse_optimizations'] = {
                'targets': self.sparse_opt_list
            }
        
        return flattened
    
    def _flatten_tree_node(self, node: TreeNode, parent_attrs: Dict):
        """Add a tree node and all its children to the flat list."""
        if node.node_type == 'Root':
            for child in node.children:
                self._flatten_tree_node(child, self.top_level_attributes)
            return
        
        # Ignore a disabled node.
        if not node.enabled:
            return
        
        # Merge the attributes. The attributes of the child have priority.
        merged_attrs = deepcopy(parent_attrs)
        merged_attrs.update(node.attributes)
        
        if node.node_type in ['Hierarchical', 'Parallel', 'Pipelined']:
            # A branch node makes no component. Process only its children.
            for child in node.children:
                self._flatten_tree_node(child, parent_attrs)
        
        elif node.node_type == 'Container':
            # Process the children with the merged attributes.
            for child in node.children:
                self._flatten_tree_node(child, merged_attrs)
        
        elif node.node_type == 'Component':
            self._flatten_component(node, merged_attrs)
        
        elif node.node_type == 'Nothing':
            # A Nothing node can have constraints. Process them.
            self._flatten_nothing(node, merged_attrs)
    
    def _flatten_component(self, node: TreeNode, merged_attrs: Dict):
        """Add one Component node to the flat component list."""
        meshX, meshY = node.calculate_accumulated_mesh()
        base_name, list_suffix, list_length = self.interpret_component_list(node.name)
        
        mesh_instances = meshX * meshY
        list_instances = list_length if list_length else 1
        total_instances = mesh_instances * list_instances
        
        # Get the full hierarchical path (without branch nodes).
        full_path = node.get_hierarchical_path()
        instance_suffix = f"[1..{total_instances}]"
        full_name_with_instances = f"{full_path}{instance_suffix}"
        
        # Add the mesh dimensions to the attributes.
        merged_attrs = deepcopy(merged_attrs)
        merged_attrs['meshX'] = meshX
        merged_attrs['meshY'] = meshY
        
        # Make the component entry.
        comp_entry = OrderedDict([
            ('name', full_name_with_instances),
            ('class', node.comp_class)
        ])
        
        if node.subclass:
            comp_entry['subclass'] = node.subclass
        
        comp_entry['attributes'] = merged_attrs
        
        # Add required_actions only if the input file specifies them.
        if node.required_actions is not None and len(node.required_actions) > 0:
            comp_entry['required_actions'] = node.required_actions
        
        # Add area_scale if the input file specifies it.
        if node.area_scale is not None:
            comp_entry['area_scale'] = node.area_scale
        
        # Add energy_scale if the input file specifies it.
        if node.energy_scale is not None:
            comp_entry['energy_scale'] = node.energy_scale
        
        comp_entry['enabled'] = True
        
        self.flat_components.append(comp_entry)
        
        # Process the constraints.
        if node.constraints is not None:
            self._process_constraints(node.name, full_name_with_instances, node.constraints)
        
        # Process the sparse optimizations.
        if node.sparse_optimizations is not None:
            self._process_sparse_optimizations(full_name_with_instances, node.sparse_optimizations)
    
    def _flatten_nothing(self, node: TreeNode, merged_attrs: Dict):
        """
        Process a Nothing node.
        A Nothing node makes no storage or compute entry, but it can have
        constraints and sparse optimizations.
        """
        # Process the constraints, if there are some.
        if node.constraints is not None:
            full_path = node.get_hierarchical_path()
            self._process_constraints(node.name, full_path, node.constraints)
        
        # Process the sparse optimizations, if there are some.
        if node.sparse_optimizations is not None:
            full_path = node.get_hierarchical_path()
            self._process_sparse_optimizations(full_path, node.sparse_optimizations)
    
    def _process_constraints(self, node_name: str, target_name: str, constraints: Dict):
        """Add the constraints of a node to the constraint list."""
        for constraint_type, constraint_value in constraints.items():
            if constraint_value is None:
                continue
            constraint_entry = deepcopy(constraint_value)
            constraint_entry['type'] = constraint_type
            constraint_entry['target'] = target_name.split('[')[0]  # Remove the instance suffix.
            
            # Change a permutation list into a string.
            if 'permutation' in constraint_entry and isinstance(constraint_entry['permutation'], list):
                constraint_entry['permutation'] = ''.join(str(p) for p in constraint_entry['permutation'])
            
            # Change a factors list into a string.
            if 'factors' in constraint_entry and isinstance(constraint_entry['factors'], list):
                constraint_entry['factors'] = ' '.join(str(f) for f in constraint_entry['factors'])
            
            self.constraint_list.append(constraint_entry)
    
    def _process_sparse_optimizations(self, target_name: str, sparse_opts: Dict):
        """Add the sparse optimizations of a node to the list."""
        sparse_entry = deepcopy(sparse_opts)
        sparse_entry['name'] = target_name.split('[')[0]  # Remove the instance suffix.
        self.sparse_opt_list.append(sparse_entry)
    
    def print_tree(self):
        """Print the hierarchy tree of the input file with box-drawing characters."""
        if not self.tree_root:
            warning(7501).emit()
            return
        
        info(7502).emit()
        print("=" * 100)
        if self.tree_root.children:
            for child in self.tree_root.children:
                self._print_tree_node(child, "", True, True)
        print("=" * 100)
    
    def _print_tree_node(self, node: TreeNode, prefix: str, is_last: bool, is_root: bool):
        """Print a tree node and all its children with the correct connectors."""
        meshX, meshY = node.calculate_accumulated_mesh()
        
        # Make the instance text for the node type.
        if node.node_type == 'Component':
            base_name, list_suffix, list_length = self.interpret_component_list(node.name)
            list_instances = list_length if list_length else 1
            total_instances = meshX * meshY * list_instances
            instance_str = f" [×{total_instances}]" if total_instances > 1 else ""
        elif node.node_type == 'Nothing':
            own_fanout = node.get_own_fanout()
            instance_str = f" [×{own_fanout}]" if own_fanout > 1 else ""
        else:
            spatial_info = []
            if node.spatial:
                if 'meshX' in node.spatial and node.spatial['meshX'] > 1:
                    spatial_info.append(f"meshX={node.spatial['meshX']}")
                if 'meshY' in node.spatial and node.spatial['meshY'] > 1:
                    spatial_info.append(f"meshY={node.spatial['meshY']}")
            instance_str = f" ({', '.join(spatial_info)})" if spatial_info else ""
        
        # Select the connector.
        if is_root:
            connector = ""
            new_prefix = ""
        else:
            connector = "└── " if is_last else "├── "
            new_prefix = prefix + ("    " if is_last else "│   ")
        
        # Make the status text.
        status_parts = []
        if not node.enabled:
            status_parts.append("DISABLED")
        
        status_str = f" [{', '.join(status_parts)}]" if status_parts else ""
        
        # Make the node text for the node type.
        if node.node_type == 'Component':
            if node.subclass:
                type_info = f"(class: {node.comp_class}/{node.subclass})"
            else:
                type_info = f"(class: {node.comp_class})"
            print(f"{prefix}{connector}{node.name}{instance_str} {type_info}{status_str}")  # nw-lint: text
        elif node.node_type == 'Container':
            print(f"{prefix}{connector}{node.name} (container){instance_str}{status_str}")  # nw-lint: text
        elif node.node_type in ['Parallel', 'Hierarchical', 'Pipelined']:
            print(f"{prefix}{connector}{node.name}")  # nw-lint: text
        elif node.node_type == 'Nothing':
            # For a Nothing node, show if it has constraints.
            constraint_info = ""
            if node.constraints:
                constraint_info = f" [has constraints]"
            print(f"{prefix}{connector}{node.name} (nothing){instance_str}{constraint_info}{status_str}")  # nw-lint: text
        
        # Print the children.
        for i, child in enumerate(node.children):
            is_last_child = (i == len(node.children) - 1)
            self._print_tree_node(child, new_prefix, is_last_child, False)
    
    def save_flattened(self, output_path: str, flattened_data: Dict):
        """Write the flat YAML structure to a file."""
        class OrderedDumper(yaml.SafeDumper):
            pass
        
        def dict_representer(dumper, data):
            return dumper.represent_mapping('tag:yaml.org,2002:map', data.items())
        
        OrderedDumper.add_representer(OrderedDict, dict_representer)
        
        with open(output_path, 'w') as f:
            yaml.dump(flattened_data, f, Dumper=OrderedDumper, 
                     default_flow_style=False, sort_keys=False, indent=4)


def flatten_accelergy_v04_yaml(
    input_yaml: str | Path,
    output_yaml: str | Path,
    *,
    print_tree: bool = False,
) -> Dict:
    """Read an Accelergy v0.4 architecture file and write the flat structure.

    Args:
        input_yaml: Path of the input YAML file.
        output_yaml: Path of the output YAML file (the flat structure).
        print_tree: If True, print a text tree of the hierarchy.

    Returns:
        The flat YAML dictionary.

    Raises:
        Exception: An error from the YAML parser or from the flattener.
    """

    in_path = Path(input_yaml)
    out_path = Path(output_yaml)

    info(7503, path=in_path).emit()

    flattener = AccelergyV04Flattener()
    content = flattener.parse_yaml(str(in_path))
    flattened = flattener.flatten_hierarchy(content)

    if print_tree:
        flattener.print_tree()

    flattener.save_flattened(str(out_path), flattened)
    
    # Print the result message.
    info(7504, path=out_path).emit()
    
    return flattened