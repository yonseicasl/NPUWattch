"""NPUWattch Database Module.

This module builds an in-memory database from flattened Accelergy v0.4 YAML files.
It extracts component information including name, class, subclass, attributes,
and instance counts for use in energy estimation workflows.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import yaml


@dataclass
class ComponentEntry:
    """Represents a single component entry in the database."""
    name: str
    base_name: str  # Name without instance suffix
    comp_class: str
    subclass: Optional[str]
    attributes: Dict[str, Any]
    instance_count: int
    enabled: bool = True
    # Estimator output columns (populated later by estimator)
    energy: Optional[float] = None
    area: Optional[float] = None
    timing: Optional[float] = None
    
    def __repr__(self) -> str:
        sub = f"/{self.subclass}" if self.subclass else ""
        return (f"ComponentEntry({self.base_name}, class={self.comp_class}{sub}, "
                f"instances={self.instance_count}, attributes={self.attributes}, "
                f"energy={self.energy}, area={self.area}, timing={self.timing})")


@dataclass
class NPUWattchDatabase:
    """
    In-memory database of architecture components extracted from flattened YAML.
    
    Attributes:
        components: List of all component entries
        version: Architecture version from the YAML
        source_file: Path to the source flattened YAML file
    """
    components: List[ComponentEntry] = field(default_factory=list)
    version: str = "0.4"
    source_file: Optional[Path] = None
    
    def __repr__(self) -> str:
        lines = [f"NPUWattchDatabase(version={self.version}, source={self.source_file})"]
        lines.append(f"  Components ({len(self.components)} total, {self.total_instances()} instances):")
        for comp in self.components:
            lines.append(f"    - {comp}")
        return "\n".join(lines)
    
    def __len__(self) -> int:
        return len(self.components)
    
    def __iter__(self):
        return iter(self.components)
    
    def get_by_name(self, name: str) -> Optional[ComponentEntry]:
        """Find a component by its base name (without instance suffix)."""
        for comp in self.components:
            if comp.base_name == name or comp.name == name:
                return comp
        return None
    
    def get_by_class(self, comp_class: str) -> List[ComponentEntry]:
        """Find all components with a specific class."""
        return [c for c in self.components if c.comp_class == comp_class]
    
    def get_by_subclass(self, subclass: str) -> List[ComponentEntry]:
        """Find all components with a specific subclass."""
        return [c for c in self.components if c.subclass == subclass]
    
    def total_instances(self) -> int:
        """Get the total number of component instances across all entries."""
        return sum(c.instance_count for c in self.components)
    
    def summary(self) -> Dict[str, Any]:
        """Get a summary of the database contents."""
        return {
            "version": self.version,
            "source_file": str(self.source_file) if self.source_file else None,
            "component_count": len(self.components),
            "total_instances": self.total_instances(),
            "classes": list(set(c.comp_class for c in self.components)),
        }


class DatabaseBuilder:
    """
    Builds an NPUWattchDatabase from flattened YAML files.
    
    The flattened YAML should have the structure:
        architecture:
            version: '0.4'
            local:
                - name: Component.Path[n..m]
                  class: class_name
                  subclass: subclass_name  # optional
                  attributes: {...}
                  enabled: true  # optional
    """
    
    # Pattern to match instance notation [n..m] at the end of name
    INSTANCE_PATTERN = re.compile(r'\[(\d+)\.\.(\d+)\]$')
    
    def __init__(self, verbose: int = 0):
        """
        Initialize the database builder.
        
        Args:
            verbose: Verbosity level (0=quiet, 1=info, 2+=detailed)
        """
        self.verbose = verbose
    
    def _parse_instance_count(self, name: str) -> tuple[str, int]:
        """
        Parse the instance count from a component name.
        
        Args:
            name: Component name, possibly with [n..m] suffix
            
        Returns:
            Tuple of (base_name, instance_count)
            
        Examples:
            "System.DRAM[1..1]" -> ("System.DRAM", 1)
            "System.PE.MAC[1..256]" -> ("System.PE.MAC", 256)
            "Component" -> ("Component", 1)
        """
        match = self.INSTANCE_PATTERN.search(name)
        if match:
            start = int(match.group(1))
            end = int(match.group(2))
            instance_count = end - start + 1
            base_name = name[:match.start()]
            return base_name, instance_count
        return name, 1
    
    def _parse_component(self, entry: Dict[str, Any]) -> Optional[ComponentEntry]:
        """
        Parse a single component entry from the YAML.
        
        Args:
            entry: Dictionary representing one component from architecture.local
            
        Returns:
            ComponentEntry or None if parsing fails
        """
        name = entry.get('name', '')
        if not name:
            return None
        
        base_name, instance_count = self._parse_instance_count(name)
        
        return ComponentEntry(
            name=name,
            base_name=base_name,
            comp_class=entry.get('class', 'unknown'),
            subclass=entry.get('subclass'),
            attributes=entry.get('attributes', {}),
            instance_count=instance_count,
            enabled=entry.get('enabled', True),
        )
    
    def build_from_yaml(self, yaml_path: Union[str, Path]) -> NPUWattchDatabase:
        """
        Build a database from a flattened YAML file.
        
        Args:
            yaml_path: Path to the flattened YAML file
            
        Returns:
            NPUWattchDatabase populated with component entries
        """
        yaml_path = Path(yaml_path)
        
        print(f"[INFO] Starting database construction from: {yaml_path}")
        
        # Load the YAML file
        with yaml_path.open('r', encoding='utf-8') as f:
            content = yaml.safe_load(f)
        
        if not content:
            print("[WARNING] Empty YAML file")
            return NPUWattchDatabase(source_file=yaml_path)
        
        # Extract architecture section
        arch = content.get('architecture', {})
        version = arch.get('version', '0.4')
        local_components = arch.get('local', [])
        
        # Build the database
        db = NPUWattchDatabase(
            version=str(version),
            source_file=yaml_path,
        )
        
        # Parse each component
        for entry in local_components:
            component = self._parse_component(entry)
            if component:
                db.components.append(component)
        
        # Output detailed info if verbose >= 1
        if self.verbose >= 1:
            self._print_database_contents(db)
        
        print(f"[INFO] Database construction complete. "
              f"Loaded {len(db)} components with {db.total_instances()} total instances.")
        
        return db
    
    def build_from_dict(self, content: Dict[str, Any], 
                        source_name: str = "<dict>") -> NPUWattchDatabase:
        """
        Build a database from an already-loaded dictionary.
        
        Args:
            content: Dictionary containing the flattened architecture
            source_name: Name to identify the source (for logging)
            
        Returns:
            NPUWattchDatabase populated with component entries
        """
        print(f"[INFO] Starting database construction from: {source_name}")
        
        # Extract architecture section
        arch = content.get('architecture', {})
        version = arch.get('version', '0.4')
        local_components = arch.get('local', [])
        
        # Build the database
        db = NPUWattchDatabase(
            version=str(version),
        )
        
        # Parse each component
        for entry in local_components:
            component = self._parse_component(entry)
            if component:
                db.components.append(component)
        
        # Output detailed info if verbose >= 2
        if self.verbose >= 2:
            self._print_database_contents(db)
        
        print(f"[INFO] Database construction complete. "
              f"Loaded {len(db)} components with {db.total_instances()} total instances.")
        
        return db
    
    def _print_database_contents(self, db: NPUWattchDatabase) -> None:
        """Print detailed database contents to console."""
        print("=" * 100)
        print(f"{'NAME':<60} {'CLASS':<20} {'SUBCLASS':<15} {'INSTANCES':>10}")
        print("-" * 100)
        
        for comp in db.components:
            subclass_str = comp.subclass if comp.subclass else "-"
            print(f"{comp.base_name:<60} {comp.comp_class:<20} {subclass_str:<15} {comp.instance_count:>10}")
        
        print("=" * 100)
        print(f"Total: {len(db)} components, {db.total_instances()} instances")
        print("=" * 100)


def build_database(
    yaml_path: Union[str, Path],
    verbose: int = 0,
) -> NPUWattchDatabase:
    """
    Convenience function to build a database from a flattened YAML file.
    
    Args:
        yaml_path: Path to the flattened YAML file
        verbose: Verbosity level (0=quiet, 1=info, 2+=detailed)
        
    Returns:
        NPUWattchDatabase populated with component entries
    """
    builder = DatabaseBuilder(verbose=verbose)
    return builder.build_from_yaml(yaml_path)


def build_database_from_dict(
    content: Dict[str, Any],
    verbose: int = 0,
    source_name: str = "<dict>",
) -> NPUWattchDatabase:
    """
    Convenience function to build a database from a dictionary.
    
    Args:
        content: Dictionary containing the flattened architecture
        verbose: Verbosity level (0=quiet, 1=info, 2+=detailed)
        source_name: Name to identify the source (for logging)
        
    Returns:
        NPUWattchDatabase populated with component entries
    """
    builder = DatabaseBuilder(verbose=verbose)
    return builder.build_from_dict(content, source_name)