"""Accelergy v0.4 Architecture YAML Flattener.

This module is intended to be invoked *by* the NPUWattch CLI (npuwattch_console),
not as a standalone script.
"""

from pathlib import Path

import yaml
from collections import OrderedDict
from copy import deepcopy
from typing import Dict, List, Any, Tuple, Optional


class TreeNode:
    """Represents a node in the architecture hierarchy tree."""
    def __init__(self, name, node_type, comp_class=None, subclass=None, 
                 spatial=None, attributes=None, required_actions=None,
                 constraints=None):
        self.name = name
        self.node_type = node_type  #'Hierarchical', 'Parallel', 'Container', 'Component', 'Nothing', 'Root'
        self.comp_class = comp_class
        self.subclass = subclass
        self.spatial = spatial or {}
        self.attributes = attributes or {}
        self.required_actions = required_actions or []
        self.constraints = constraints
        self.children = []
        self.parent = None
        
    def add_child(self, child):
        """Add a child node."""
        child.parent = self
        self.children.append(child)
        
    def get_hierarchical_path(self):
        """
        Get the full hierarchical path using dot notation.
        Skip all branch nodes (Hierarchical, Parallel, Root) in the path.
        Only include Container and Component nodes.
        """
        #Build path by walking up, collecting only Container/Component names
        path_parts = []
        current = self
        
        while current is not None and current.node_type != 'Root':
            if current.node_type in ['Container', 'Component']:
                path_parts.insert(0, current.name)
            #Skip branch nodes: Hierarchical, Parallel
            current = current.parent
        
        return '.'.join(path_parts)
    
    def calculate_accumulated_mesh(self):
        """Calculate accumulated mesh dimensions from root to this node."""
        meshX, meshY = 1, 1
        node = self
        while node is not None:
            #Only accumulate from Container nodes with spatial dimensions
            if node.node_type == 'Container' and node.spatial:
                meshX *= node.spatial.get('meshX', 1)
                meshY *= node.spatial.get('meshY', 1)
            node = node.parent
        return meshX, meshY
    
    def __repr__(self):
        return f"TreeNode({self.name}, {self.node_type})"


class AccelergyV04Flattener:
    """Flattener for Accelergy v0.4 architecture YAML files."""
    
    def __init__(self):
        self.flat_components = []
        self.tree_root = None
        self.top_level_attributes = {}
        
    def parse_yaml(self, filepath: str) -> Dict:
        """Load and parse a YAML file with custom Accelergy tags."""
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
        
        def nothing_constructor(loader, node):
            value = loader.construct_mapping(node, deep=True)
            value['_type'] = 'Nothing'
            return value
        
        yaml.SafeLoader.add_constructor('!Container', container_constructor)
        yaml.SafeLoader.add_constructor('!Component', component_constructor)
        yaml.SafeLoader.add_constructor('!Parallel', parallel_constructor)
        yaml.SafeLoader.add_constructor('!Hierarchical', hierarchical_constructor)
        yaml.SafeLoader.add_constructor('!Nothing', nothing_constructor)
        
        with open(filepath, 'r') as f:
            return yaml.safe_load(f)
    
    def interpret_component_list(self, name: str) -> Tuple[str, Optional[str], Optional[int]]:
        """Parse component name to detect list notation [start..end]."""
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
        """Build the hierarchy tree from YAML content."""
        arch = content.get('architecture', {})
        root = TreeNode('root', 'Root')
        
        if 'nodes' in arch:
            nodes = arch['nodes']
            
            #First node is typically the top-level container
            if nodes and nodes[0].get('_type') == 'Container':
                top_container = nodes[0]
                top_name = top_container.get('name', 'System')
                top_attrs = top_container.get('attributes', {})
                self.top_level_attributes = deepcopy(top_attrs)
                
                top_node = TreeNode(
                    name=f"{top_name}_top_level",
                    node_type='Container',
                    attributes=top_attrs
                )
                root.add_child(top_node)
                
                #Process remaining nodes as hierarchical
                self._process_hierarchical_nodes(nodes[1:], top_node)
            else:
                top_node = TreeNode('System_top_level', 'Container')
                root.add_child(top_node)
                self._process_hierarchical_nodes(nodes, top_node)
        
        return root
    
    def _process_hierarchical_nodes(self, nodes: List[Dict], parent: TreeNode):
        """
        Process nodes in hierarchical mode (sequential nesting).
        Each Container becomes the scope for subsequent nodes.
        """
        scope_stack = [parent]
        
        for node in nodes:
            node_type = node.get('_type', 'Component')
            
            if node_type == 'Hierarchical':
                #Create a hierarchical branch node
                hier_node = TreeNode(name='(hierarchical)', node_type='Hierarchical')
                scope_stack[-1].add_child(hier_node)
                
                #Process children hierarchically
                if 'nodes' in node:
                    self._process_hierarchical_nodes(node['nodes'], hier_node)
            
            elif node_type == 'Parallel':
                #Create a parallel branch node
                parallel_node = TreeNode(name='(parallel)', node_type='Parallel')
                scope_stack[-1].add_child(parallel_node)
                
                #Process children - each is a sibling
                if 'nodes' in node:
                    for child_node in node['nodes']:
                        self._process_node(child_node, parallel_node)
            
            elif node_type == 'Container':
                #Create container and push to scope
                container_node = self._create_container_node(node)
                scope_stack[-1].add_child(container_node)
                scope_stack.append(container_node)
            
            elif node_type == 'Component':
                #Create component in current scope
                component_node = self._create_component_node(node)
                scope_stack[-1].add_child(component_node)
            
            elif node_type == 'Nothing':
                #Create nothing node
                nothing_node = TreeNode(name='(unnamed)', node_type='Nothing')
                scope_stack[-1].add_child(nothing_node)
    
    def _process_node(self, node: Dict, parent: TreeNode):
        """Process a single node (used for Parallel children and Hierarchical children)."""
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
        
        elif node_type == 'Container':
            container_node = self._create_container_node(node)
            parent.add_child(container_node)
        
        elif node_type == 'Component':
            component_node = self._create_component_node(node)
            parent.add_child(component_node)
        
        elif node_type == 'Nothing':
            nothing_node = TreeNode(name='(unnamed)', node_type='Nothing')
            parent.add_child(nothing_node)
    
    def _create_container_node(self, node: Dict) -> TreeNode:
        """Create a Container tree node."""
        return TreeNode(
            name=node.get('name', 'container'),
            node_type='Container',
            spatial=node.get('spatial', {}),
            attributes=node.get('attributes', {}),
            constraints=node.get('constraints', None)
        )
    
    def _create_component_node(self, node: Dict) -> TreeNode:
        """Create a Component tree node."""
        return TreeNode(
            name=node.get('name', 'component'),
            node_type='Component',
            comp_class=node.get('class', 'unknown'),
            subclass=node.get('subclass', None),
            attributes=node.get('attributes', {}),
            required_actions=node.get('required_actions', None),
            constraints=node.get('constraints', None)
        )
    
    def flatten_hierarchy(self, content: Dict) -> Dict:
        """Main entry point to flatten architecture hierarchy."""
        arch = content.get('architecture', {})
        version = arch.get('version', '0.4')
        
        #Build the hierarchy tree
        self.tree_root = self.build_hierarchy_tree(content)
        
        #Flatten the tree
        self._flatten_tree_node(self.tree_root, {})
        
        #Build flattened YAML structure
        flattened = {
            'architecture': {
                'version': str(version),
                'local': self.flat_components
            }
        }
        
        return flattened
    
    def _flatten_tree_node(self, node: TreeNode, parent_attrs: Dict):
        """Recursively flatten a tree node."""
        if node.node_type == 'Root':
            for child in node.children:
                self._flatten_tree_node(child, self.top_level_attributes)
            return
        
        #Merge attributes - child attributes override parent
        merged_attrs = deepcopy(parent_attrs)
        merged_attrs.update(node.attributes)
        
        if node.node_type in ['Hierarchical', 'Parallel']:
            #Branch nodes don't create components, just process children
            for child in node.children:
                self._flatten_tree_node(child, parent_attrs)
        
        elif node.node_type == 'Container':
            #Process children with merged attributes
            for child in node.children:
                self._flatten_tree_node(child, merged_attrs)
        
        elif node.node_type == 'Component':
            meshX, meshY = node.calculate_accumulated_mesh()
            base_name, list_suffix, list_length = self.interpret_component_list(node.name)
            
            mesh_instances = meshX * meshY
            list_instances = list_length if list_length else 1
            total_instances = mesh_instances * list_instances
            
            #Get full hierarchical path (skipping branch nodes)
            full_path = node.get_hierarchical_path()
            instance_suffix = f"[1..{total_instances}]"
            full_name_with_instances = f"{full_path}{instance_suffix}"
            
            #Add mesh information to attributes
            merged_attrs['meshX'] = meshX
            merged_attrs['meshY'] = meshY
            
            #Build component entry
            comp_entry = OrderedDict([
                ('name', full_name_with_instances),
                ('class', node.comp_class)
            ])
            
            if node.subclass:
                comp_entry['subclass'] = node.subclass
            
            comp_entry['attributes'] = merged_attrs
            
            #Only add required_actions if specified in the input YAML
            if node.required_actions is not None and len(node.required_actions) > 0:
                comp_entry['required_actions'] = node.required_actions
            
            #Only add constraints if specified
            if node.constraints is not None:
                comp_entry['constraints'] = node.constraints
            
            comp_entry['enabled'] = True
            
            self.flat_components.append(comp_entry)
    
    def print_tree(self):
        """Print the hierarchy tree from input YAML using ASCII box-drawing characters."""
        if not self.tree_root:
            print("No tree to display")
            return
        
        print("[INFO] Architecture Hierarchy Tree:")
        print("=" * 80)
        if self.tree_root.children:
            for child in self.tree_root.children:
                self._print_tree_node(child, "", True, True)
        print("=" * 80)
    
    def _print_tree_node(self, node: TreeNode, prefix: str, is_last: bool, is_root: bool):
        """Recursively print tree node with proper connectors."""
        meshX, meshY = node.calculate_accumulated_mesh()
        
        if node.node_type == 'Component':
            base_name, list_suffix, list_length = self.interpret_component_list(node.name)
            list_instances = list_length if list_length else 1
            total_instances = meshX * meshY * list_instances
            instance_str = f" [×{total_instances}]" if total_instances > 1 else ""
        else:
            spatial_info = []
            if node.spatial:
                if 'meshX' in node.spatial and node.spatial['meshX'] > 1:
                    spatial_info.append(f"meshX={node.spatial['meshX']}")
                if 'meshY' in node.spatial and node.spatial['meshY'] > 1:
                    spatial_info.append(f"meshY={node.spatial['meshY']}")
            instance_str = f" ({', '.join(spatial_info)})" if spatial_info else ""
        
        if is_root:
            connector = ""
            new_prefix = ""
        else:
            connector = "└── " if is_last else "├── "
            new_prefix = prefix + ("    " if is_last else "│   ")
        
        #Format node info
        if node.node_type == 'Component':
            if node.subclass:
                type_info = f"(class: {node.comp_class}/{node.subclass})"
            else:
                type_info = f"(class: {node.comp_class})"
            print(f"{prefix}{connector}{node.name}{instance_str} {type_info}")
        elif node.node_type == 'Container':
            print(f"{prefix}{connector}{node.name} (container){instance_str}")
        elif node.node_type in ['Parallel', 'Hierarchical']:
            print(f"{prefix}{connector}{node.name}")
        elif node.node_type == 'Nothing':
            print(f"{prefix}{connector}{node.name} (nothing)")
        
        #Print children
        for i, child in enumerate(node.children):
            is_last_child = (i == len(node.children) - 1)
            self._print_tree_node(child, new_prefix, is_last_child, False)
    
    def save_flattened(self, output_path: str, flattened_data: Dict):
        """Save flattened YAML to file."""
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
    """Flatten an Accelergy v0.4 architecture YAML file.

    Args:
        input_yaml: Input YAML file path.
        output_yaml: Output YAML file path (flattened structure).
        print_tree: If True, print an ASCII tree for the parsed hierarchy.

    Returns:
        The flattened YAML dictionary.

    Raises:
        Exception: Propagates YAML parsing / flattening errors.
    """
    in_path = Path(input_yaml)
    out_path = Path(output_yaml)

    flattener = AccelergyV04Flattener()
    content = flattener.parse_yaml(str(in_path))
    flattened = flattener.flatten_hierarchy(content)

    if print_tree:
        flattener.print_tree()

    flattener.save_flattened(str(out_path), flattened)
    
    # Print success message
    print(f"[INFO] Flattened YAML written to: {out_path}")
    
    return flattened