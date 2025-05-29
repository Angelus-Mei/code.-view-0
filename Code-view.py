
import ast
import os
import graphviz
import sys
import subprocess # For opening files
import collections # For defaultdict

from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QPushButton,
    QLabel, QFileDialog, QTextEdit, QMessageBox,
    QHBoxLayout, QComboBox, QMenuBar, QStatusBar,
    QGridLayout, QFrame
)
from PySide6.QtCore import Qt, QSettings
from PySide6.QtGui import QAction, QFont, QIcon, QPalette, QColor

# --- AST Parsing Logic (Significantly Enhanced) ---
class CodeStructureExtractor(ast.NodeVisitor):
    def __init__(self):
        self.structure = {
            "module_name": None,
            "global_variables": [],
            "classes": [],
            "functions": [],
            "imports": {
                "direct": [],
                "from": []
            },
            "calls": collections.defaultdict(set) # Source -> Destination calls
        }
        self.current_scope = [] # Stack to track current function/class scope

    def _add_call(self, caller_id, callee_id):
        self.structure["calls"][caller_id].add(callee_id)

    def _get_current_scope_id(self):
        if self.current_scope:
            return ".".join(self.current_scope)
        return self.structure["module_name"] # Module level calls

    def _get_full_name(self, node):
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            return f"{self._get_full_name(node.value)}.{node.attr}"
        elif isinstance(node, ast.Call):
            return f"{self._get_full_name(node.func)}(...)"
        return "<?>"

    def visit_Module(self, node):
        self.structure["module_name"] = "Module" # Default if not set later from filename
        self.generic_visit(node)

    def visit_ClassDef(self, node):
        class_info = {
            "name": node.name,
            "methods": [],
            "bases": [self._get_full_name(base) for base in node.bases if isinstance(base, (ast.Name, ast.Attribute))],
            "docstring": ast.get_docstring(node),
            "attributes": [],
            "decorators": [self._get_full_name(d) for d in node.decorator_list if self._get_full_name(d) is not None]
        }
        self.structure["classes"].append(class_info)

        self.current_scope.append(node.name)
        self.generic_visit(node)
        self.current_scope.pop()

    def visit_FunctionDef(self, node):
        args_list = []
        for arg in node.args.posonlyargs + node.args.args + node.args.kwonlyargs:
            arg_name = arg.arg
            arg_annotation = ""
            if arg.annotation:
                arg_annotation = f": {self._get_full_name(arg.annotation)}"
            args_list.append(f"{arg_name}{arg_annotation}")

        # Add default values
        for i, default in enumerate(node.args.defaults[::-1]):
            args_list[len(args_list) - 1 - i] += f"={self._get_full_name(default)}"
        
        # Add keyword-only argument defaults
        if node.args.kwonlyargs:
            for i, default in enumerate(node.args.kw_defaults[::-1]):
                if default:
                    args_list[len(args_list) - len(node.args.kwonlyargs) - 1 - i] += f"={self._get_full_name(default)}"

        return_annotation = ""
        if node.returns:
            return_annotation = f" -> {self._get_full_name(node.returns)}"

        func_info = {
            "name": node.name,
            "args": args_list,
            "docstring": ast.get_docstring(node),
            "return_annotation": return_annotation,
            "decorators": [self._get_full_name(d) for d in node.decorator_list if self._get_full_name(d) is not None],
            "calls_made": set() # Calls originating from this function/method
        }

        if self.current_scope and self.current_scope[-1] in [cls["name"] for cls in self.structure["classes"]]:
            # This is a method
            class_name = self.current_scope[-1]
            for cls in self.structure["classes"]:
                if cls["name"] == class_name:
                    cls["methods"].append(func_info)
                    break
        else:
            # This is a global function
            self.structure["functions"].append(func_info)
        
        self.current_scope.append(node.name)
        self.generic_visit(node)
        self.current_scope.pop()

    def visit_Assign(self, node):
        for target in node.targets:
            if isinstance(target, ast.Name):
                var_info = {
                    "name": target.id,
                    "value": self._get_full_name(node.value)
                }
                if self.current_scope: # Assume it's an attribute if in a class scope
                    scope_name = self.current_scope[-1]
                    for cls in self.structure["classes"]:
                        if cls["name"] == scope_name:
                            cls["attributes"].append(var_info)
                            break
                else: # Global variable
                    self.structure["global_variables"].append(var_info)
        self.generic_visit(node)

    def visit_AnnAssign(self, node):
        if isinstance(node.target, ast.Name):
            var_info = {
                "name": node.target.id,
                "annotation": self._get_full_name(node.annotation),
                "value": self._get_full_name(node.value) if node.value else None
            }
            if self.current_scope:
                scope_name = self.current_scope[-1]
                for cls in self.structure["classes"]:
                    if cls["name"] == scope_name:
                        cls["attributes"].append(var_info)
                        break
            else:
                self.structure["global_variables"].append(var_info)
        self.generic_visit(node)

    def visit_Import(self, node):
        for alias in node.names:
            self.structure["imports"]["direct"].append(alias.name)
        self.generic_visit(node)

    def visit_ImportFrom(self, node):
        module = node.module if node.module else ""
        for alias in node.names:
            self.structure["imports"]["from"].append(f"{module}.{alias.name}" if module else alias.name)
        self.generic_visit(node)

    def visit_Call(self, node):
        caller_id = self._get_current_scope_id()
        callee_id = self._get_full_name(node.func)
        self._add_call(caller_id, callee_id)
        self.generic_visit(node)
    
    # Basic control flow for graph labeling (can be expanded)
    def visit_If(self, node):
        caller_id = self._get_current_scope_id()
        self._add_call(caller_id, f"Condition: {self._get_full_name(node.test)}")
        self.generic_visit(node)
    
    def visit_For(self, node):
        caller_id = self._get_current_scope_id()
        self._add_call(caller_id, f"For Loop: {self._get_full_name(node.iter)}")
        self.generic_visit(node)

    def visit_While(self, node):
        caller_id = self._get_current_scope_id()
        self._add_call(caller_id, f"While Loop: {self._get_full_name(node.test)}")
        self.generic_visit(node)

def parse_python_file(filepath):
    if not os.path.exists(filepath):
        return None, f"Error: File does not exist '{filepath}'"

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            source_code = f.read()
    except Exception as e:
        return None, f"Error: Could not read file '{filepath}': {e}"

    try:
        tree = ast.parse(source_code)
        extractor = CodeStructureExtractor()
        extractor.structure["module_name"] = os.path.basename(filepath).replace(".py", "")
        extractor.visit(tree)
        return extractor.structure, None
    except SyntaxError as e:
        return None, f"Parsing error: File '{filepath}' contains syntax error: {e}"
    except Exception as e:
        return None, f"An unknown error occurred during parsing: {e}"

def format_structure_text(structure):
    if not structure:
        return "No code structure to display."

    output = []
    output.append(f"--- Module: {structure['module_name']} ---")

    if structure["imports"]["direct"] or structure["imports"]["from"]:
        output.append("\n--- Imports ---")
        for imp in sorted(list(set(structure["imports"]["direct"]))):
            output.append(f"  - import {imp}")
        for imp_from in sorted(list(set(structure["imports"]["from"]))):
            parts = imp_from.split('.', 1)
            if len(parts) > 1:
                output.append(f"  - from {parts[0]} import {parts[1]}")
            else:
                output.append(f"  - from . import {parts[0]}")

    if structure["global_variables"]:
        output.append("\n--- Global Variables ---")
        for var in structure["global_variables"]:
            var_line = f"  - {var['name']}"
            if 'annotation' in var and var['annotation']:
                var_line += f": {var['annotation']}"
            if var['value'] is not None:
                var_line += f" = {var['value']}"
            output.append(var_line)

    if structure["functions"]:
        output.append("\n--- Global Functions ---")
        for func in structure["functions"]:
            decorators_str = "".join([f"  @{d}\n" for d in func['decorators']]) if func['decorators'] else ""
            output.append(f"{decorators_str}  def {func['name']}({', '.join(func['args'])}){func['return_annotation']}")
            if func['docstring']:
                output.append(f"    Doc: \"\"\"{func['docstring'].strip().splitlines()[0]}\"\"\"")
            
            func_id = f"{structure['module_name']}.{func['name']}"
            if func_id in structure["calls"] and structure["calls"][func_id]:
                output.append("    Calls:")
                for callee in sorted(list(structure["calls"][func_id])):
                    output.append(f"      - {callee}")


    if structure["classes"]:
        output.append("\n--- Classes ---")
        for cls in structure["classes"]:
            bases_str = f"({', '.join(cls['bases'])})" if cls['bases'] else ""
            decorators_str = "".join([f"  @{d}\n" for d in cls['decorators']]) if cls['decorators'] else ""
            output.append(f"{decorators_str}  class {cls['name']}{bases_str}:")
            if cls['docstring']:
                output.append(f"    Doc: \"\"\"{cls['docstring'].strip().splitlines()[0]}\"\"\"")

            if cls["attributes"]:
                output.append("    --- Class Attributes ---")
                for attr in cls["attributes"]:
                    attr_line = f"    - {attr['name']}"
                    if 'annotation' in attr and attr['annotation']:
                        attr_line += f": {attr['annotation']}"
                    if attr['value'] is not None:
                        attr_line += f" = {attr['value']}"
                    output.append(attr_line)

            if cls["methods"]:
                output.append("    --- Methods ---")
                for method in cls["methods"]:
                    decorators_str = "".join([f"      @{d}\n" for d in method['decorators']]) if method['decorators'] else ""
                    output.append(f"{decorators_str}      def {method['name']}({', '.join(method['args'])}){method['return_annotation']}")
                    if method['docstring']:
                        output.append(f"        Doc: \"\"\"{method['docstring'].strip().splitlines()[0]}\"\"\"")
                    
                    method_id = f"{structure['module_name']}.{cls['name']}.{method['name']}"
                    if method_id in structure["calls"] and structure["calls"][method_id]:
                        output.append("        Calls:")
                        for callee in sorted(list(structure["calls"][method_id])):
                            output.append(f"          - {callee}")
    
    # Module-level calls (e.g., direct calls outside functions/classes)
    module_calls_key = structure["module_name"]
    if module_calls_key in structure["calls"] and structure["calls"][module_calls_key]:
        output.append("\n--- Module-Level Calls ---")
        for callee in sorted(list(structure["calls"][module_calls_key])):
            output.append(f"  - {callee}")

    return "\n".join(output)

def generate_graph_visualization(structure, output_filepath, format="png"):
    if not structure:
        return None, "No graph can be generated."

    dot = graphviz.Digraph(
        comment=f'Code Structure of {structure["module_name"]}',
        graph_attr={
            'rankdir': 'LR', # Left to Right
            'overlap': 'false',
            'splines': 'true',
            'bgcolor': 'transparent'
        },
        node_attr={
            'fontsize': '10',
            'fontname': 'Helvetica',
            'shape': 'box',
            'style': 'filled'
        },
        edge_attr={'fontsize': '8', 'fontname': 'Helvetica'}
    )

    # Use a set to keep track of added nodes to avoid duplicates and simplify call connections
    all_nodes = set()
    
    # Module Cluster
    with dot.subgraph(name=f'cluster_module_{structure["module_name"]}') as c:
        c.attr(label=f'Module: {structure["module_name"]}', color='blue', style='rounded,filled', fillcolor='#E0FFFF')
        module_id = f"module_{structure['module_name']}"
        c.node(module_id, f'Module: {structure["module_name"]}', shape='folder', style='filled', fillcolor='#ADD8E6')
        all_nodes.add(module_id)

        # Global Variables
        if structure["global_variables"]:
            gv_node_id = f"{module_id}_globals"
            c.node(gv_node_id, "Global Variables", shape='note', style='filled', fillcolor='grey', fontcolor='white')
            c.edge(module_id, gv_node_id, label='defines')
            all_nodes.add(gv_node_id)


        # Global Functions
        for func in structure["functions"]:
            func_label = f"Function: {func['name']}(\n{', '.join(func['args'])}){func['return_annotation']}"
            if func['decorators']:
                func_label = f"Decorators: {', '.join(func['decorators'])}\n" + func_label
            func_id = f"{module_id}.{func['name']}"
            c.node(func_id, func_label, shape='ellipse', style='filled', fillcolor='#90EE90') # Light Green
            c.edge(module_id, func_id, label='contains')
            all_nodes.add(func_id)

    # Classes Subgraphs
    for cls in structure["classes"]:
        class_id = f"{module_id}.{cls['name']}"
        with dot.subgraph(name=f'cluster_class_{cls["name"]}') as c_cls:
            bases_str = f"({', '.join(cls['bases'])})" if cls['bases'] else ""
            decorators_str = f"Decorators: {', '.join(cls['decorators'])}\n" if cls['decorators'] else ""
            c_cls.attr(label=f'{decorators_str}Class: {cls["name"]}{bases_str}', color='darkgreen', style='rounded,filled', fillcolor='#FFFACD') # Lemon Chiffon
            
            c_cls.node(class_id, f'Class: {cls["name"]}{bases_str}', shape='component', style='filled', fillcolor='#FFD700') # Gold
            all_nodes.add(class_id)
            dot.edge(module_id, class_id, label='contains') # Link class to module

            # Class Attributes
            for attr in cls["attributes"]:
                attr_label = f"Attribute: {attr['name']}"
                if 'annotation' in attr and attr['annotation']:
                    attr_label += f": {attr['annotation']}"
                if attr['value'] is not None:
                    attr_label += f" = {attr['value']}"
                attr_id = f"{class_id}.{attr['name']}"
                c_cls.node(attr_id, attr_label, shape='rectangle', style='filled', fillcolor='#D3D3D3') # Light Gray
                c_cls.edge(class_id, attr_id, label='has attribute')
                all_nodes.add(attr_id)

            # Methods
            for method in cls["methods"]:
                method_id = f"{class_id}.{method['name']}"
                method_label = f"Method: {method['name']}(\n{', '.join(method['args'])}){method['return_annotation']}"
                if method['decorators']:
                    method_label = f"Decorators: {', '.join(method['decorators'])}\n" + method_label
                c_cls.node(method_id, method_label, shape='octagon', style='filled', fillcolor='#FFB6C1') # Light Pink
                c_cls.edge(class_id, method_id, label='contains method')
                all_nodes.add(method_id)

    # --- Add all recognized nodes to the graph even if they are just targets of a call ---
    # This helps when drawing edges to external/imported entities
    # Note: this might create "floating" nodes for unparsed external calls
    for caller, callees in structure["calls"].items():
        for callee in callees:
            if callee not in all_nodes:
                # Add a generic node for external calls or unparsed elements
                dot.node(callee, callee, shape='box', style='dashed', color='gray', fillcolor='white')
                all_nodes.add(callee)
    
    # --- Add Call Edges ---
    # Important: Ensure both source and target nodes exist before adding an edge
    for caller_raw, callees_raw in structure["calls"].items():
        # Determine the full ID of the caller within the graph context
        caller_parts = caller_raw.split('.')
        caller_id = ""
        if len(caller_parts) == 1: # Module-level function or global call
            caller_id = f"module_{structure['module_name']}.{caller_parts[0]}" if caller_parts[0] != structure['module_name'] else f"module_{structure['module_name']}"
        elif len(caller_parts) == 2: # Class method
            caller_id = f"module_{structure['module_name']}.{caller_parts[0]}.{caller_parts[1]}"
        elif len(caller_parts) == 3: # Nested method (unlikely with current AST visitor but for robustness)
             caller_id = f"module_{structure['module_name']}.{caller_parts[0]}.{caller_parts[1]}.{caller_parts[2]}"


        if caller_id not in all_nodes:
            # If the caller itself wasn't directly found (e.g., module-level calls from the base module ID)
            if caller_raw == structure["module_name"] and f"module_{structure['module_name']}" in all_nodes:
                caller_id = f"module_{structure['module_name']}"
            else:
                dot.node(caller_id, caller_raw, shape='box', style='dashed', color='red', fillcolor='white') # Indicate missing source for debugging
                all_nodes.add(caller_id)
        
        for callee in callees_raw:
            # Determine the full ID of the callee (could be internal or external)
            callee_id = callee # Default to raw name for external/unresolved calls
            
            # Check if callee is a known internal function/method/class
            # This is a heuristic and might need more robust lookup for complex structures
            if f"module_{structure['module_name']}.{callee}" in all_nodes:
                callee_id = f"module_{structure['module_name']}.{callee}"
            else:
                # Try to find if it's a method of an existing class
                for cls in structure["classes"]:
                    if f"module_{structure['module_name']}.{cls['name']}.{callee}" in all_nodes:
                        callee_id = f"module_{structure['module_name']}.{cls['name']}.{callee}"
                        break
            
            if caller_id and callee_id and caller_id != callee_id: # Avoid self-loops for now
                dot.edge(caller_id, callee_id, label='calls', color='purple')

    # Add inheritance edges explicitly (already done within class subgraph, but reinforcing direct link for clarity)
    for cls in structure["classes"]:
        class_id = f"module_{structure['module_name']}.{cls['name']}"
        for base in cls['bases']:
            base_id = f"module_{structure['module_name']}.{base}" # Assume base is in current module for now
            if base_id not in all_nodes: # If base class not defined in current module, add it as a generic node
                dot.node(base_id, base, shape='box', style='dashed', color='grey', fillcolor='white')
                all_nodes.add(base_id)
            dot.edge(base_id, class_id, style='dashed', arrowhead='empty', label='inherits')


    try:
        full_output_path = dot.render(os.path.splitext(output_filepath)[0], format=format, view=False, cleanup=True)
        return full_output_path, f"Visualization graph saved to: {full_output_path}"
    except graphviz.backend.ExecutableNotFound:
        return None, "Error: Graphviz executable (dot) not found. Please ensure Graphviz is installed and added to your system's PATH."
    except Exception as e:
        return None, f"Error generating graph: {e}"

# --- GUI Application (Mostly Unchanged, but with minor updates for new features) ---
class CodeVisualizerApp(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Python Code Structure Visualizer")
        self.setGeometry(100, 100, 900, 700) # Larger window for more details

        self.current_filepath = ""
        self.last_generated_graph_path = ""
        self.settings = QSettings("MyCompany", "CodeVisualizer")

        self.init_ui()
        self.load_settings()

    def init_ui(self):
        main_layout = QVBoxLayout(self)

        # Menu Bar
        self.menu_bar = QMenuBar(self)
        self.file_menu = self.menu_bar.addMenu("File")
        self.view_menu = self.menu_bar.addMenu("View")
        self.help_menu = self.menu_bar.addMenu("Help")

        # File Menu Actions
        self.select_file_action = QAction("Select File...", self)
        self.select_file_action.triggered.connect(self.select_file)
        self.file_menu.addAction(self.select_file_action)

        self.exit_action = QAction("Exit", self)
        self.exit_action.triggered.connect(self.close)
        self.file_menu.addAction(self.exit_action)

        # View Menu Actions
        self.toggle_theme_action = QAction("Toggle Dark/Light Theme", self)
        self.toggle_theme_action.triggered.connect(self.toggle_theme)
        self.view_menu.addAction(self.toggle_theme_action)

        # Help Menu Actions
        self.about_action = QAction("About", self)
        self.about_action.triggered.connect(self.show_about_dialog)
        self.help_menu.addAction(self.about_action)

        main_layout.setMenuBar(self.menu_bar)

        # Top Section: File Path Display and Controls
        top_frame = QFrame(self)
        top_layout = QGridLayout(top_frame)

        self.file_path_label = QLabel("No file selected")
        self.file_path_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.file_path_label.setFont(QFont("Arial", 12))
        top_layout.addWidget(self.file_path_label, 0, 0, 1, 3)

        self.select_file_btn = QPushButton("Select Python File")
        self.select_file_btn.clicked.connect(self.select_file)
        top_layout.addWidget(self.select_file_btn, 1, 0)

        self.show_text_btn = QPushButton("Show Text Structure")
        self.show_text_btn.clicked.connect(self.show_text_structure)
        top_layout.addWidget(self.show_text_btn, 1, 1)

        self.generate_graph_btn = QPushButton("Generate Graph")
        self.generate_graph_btn.clicked.connect(self.generate_graph_visualization)
        top_layout.addWidget(self.generate_graph_btn, 1, 2)

        top_layout.addWidget(QLabel("Graph Format:"), 2, 0)
        self.graph_format_combo = QComboBox(self)
        self.graph_format_combo.addItems(["png", "svg", "pdf", "dot"])
        self.graph_format_combo.setCurrentText("png")
        top_layout.addWidget(self.graph_format_combo, 2, 1)

        self.open_graph_btn = QPushButton("Open Generated Graph")
        self.open_graph_btn.clicked.connect(self.open_last_generated_graph)
        self.open_graph_btn.setEnabled(False)
        top_layout.addWidget(self.open_graph_btn, 2, 2)

        main_layout.addWidget(top_frame)

        # Text Output Area
        self.output_text_area = QTextEdit(self)
        self.output_text_area.setReadOnly(True)
        self.output_text_area.setFont(QFont("Monospace", 10))
        main_layout.addWidget(self.output_text_area)

        # Status Bar
        self.status_bar = QStatusBar(self)
        main_layout.addWidget(self.status_bar)
        self.update_status("Ready to visualize your Python code.")

    def load_settings(self):
        theme = self.settings.value("theme", "light")
        if theme == "dark":
            self.set_dark_theme()
        else:
            self.set_light_theme()

    def save_settings(self):
        if self.palette().color(QPalette.ColorRole.Window).name() == "#353535":
            self.settings.setValue("theme", "dark")
        else:
            self.settings.setValue("theme", "light")

    def toggle_theme(self):
        if self.palette().color(QPalette.ColorRole.Window).name() == "#353535":
            self.set_light_theme()
        else:
            self.set_dark_theme()
        self.save_settings()

    def set_light_theme(self):
        app.setPalette(QPalette())
        self.update_status("Theme set to Light.", "green")

    def set_dark_theme(self):
        palette = QPalette()
        palette.setColor(QPalette.ColorRole.Window, QColor(53, 53, 53))
        palette.setColor(QPalette.ColorRole.WindowText, QColor(255, 255, 255))
        palette.setColor(QPalette.ColorRole.Base, QColor(25, 25, 25))
        palette.setColor(QPalette.ColorRole.AlternateBase, QColor(53, 53, 53))
        palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(255, 255, 255))
        palette.setColor(QPalette.ColorRole.ToolTipText, QColor(255, 255, 255))
        palette.setColor(QPalette.ColorRole.Text, QColor(255, 255, 255))
        palette.setColor(QPalette.ColorRole.Button, QColor(53, 53, 53))
        palette.setColor(QPalette.ColorRole.ButtonText, QColor(255, 255, 255))
        palette.setColor(QPalette.ColorRole.BrightText, QColor(255, 0, 0))
        palette.setColor(QPalette.ColorRole.Link, QColor(42, 130, 218))
        palette.setColor(QPalette.ColorRole.Highlight, QColor(42, 130, 218))
        palette.setColor(QPalette.ColorRole.HighlightedText, QColor(0, 0, 0))
        app.setPalette(palette)
        self.update_status("Theme set to Dark.", "green")

    def update_status(self, message, color="black"):
        self.status_bar.showMessage(message)

    def log_output(self, message):
        self.output_text_area.setPlainText(message)

    def select_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Python File",
            os.path.expanduser("~"),
            "Python files (*.py);;All files (*.*)"
        )

        if file_path:
            self.current_filepath = file_path
            self.file_path_label.setText(f"File selected: {os.path.basename(self.current_filepath)}")
            self.log_output("File selected. Click buttons to visualize.")
            self.update_status("File successfully selected.", "green")
            self.open_graph_btn.setEnabled(False)
        else:
            self.current_filepath = ""
            self.file_path_label.setText("No file selected")
            self.log_output("No file selected.")
            self.update_status("File selection cancelled.", "red")
            self.open_graph_btn.setEnabled(False)

    def show_text_structure(self):
        if not self.current_filepath or not os.path.exists(self.current_filepath):
            QMessageBox.warning(self, "Warning", "Please select a valid Python file first!")
            self.update_status("Error: No file selected.", "red")
            return

        self.update_status(f"Parsing '{os.path.basename(self.current_filepath)}'...", "blue")
        structure_data, error_message = parse_python_file(self.current_filepath)

        if structure_data:
            text_output = format_structure_text(structure_data)
            self.log_output(text_output)
            self.update_status("Text structure displayed successfully.", "green")
        else:
            self.log_output(f"Parsing failed: {error_message}")
            QMessageBox.critical(self, "Parsing Error", error_message)
            self.update_status("Parsing failed.", "red")

    def generate_graph_visualization(self):
        if not self.current_filepath or not os.path.exists(self.current_filepath):
            QMessageBox.warning(self, "Warning", "Please select a valid Python file first!")
            self.update_status("Error: No file selected.", "red")
            return

        selected_format = self.graph_format_combo.currentText()
        default_filename = os.path.splitext(os.path.basename(self.current_filepath))[0] + f"_structure.{selected_format}"
        
        save_filepath, _ = QFileDialog.getSaveFileName(
            self,
            "Save Graph As",
            os.path.join(os.path.dirname(self.current_filepath), default_filename),
            f"Graphviz {selected_format.upper()} files (*.{selected_format});;All Files (*.*)"
        )

        if not save_filepath:
            self.update_status("Graph saving cancelled.", "red")
            return

        self.update_status(f"Generating graph for '{os.path.basename(self.current_filepath)}' in {selected_format.upper()} format...", "blue")
        structure_data, parse_error = parse_python_file(self.current_filepath)

        if structure_data:
            full_path, graph_message = generate_graph_visualization(structure_data, save_filepath, selected_format)

            if full_path:
                self.last_generated_graph_path = full_path
                self.open_graph_btn.setEnabled(True)
                self.log_output(graph_message)
                QMessageBox.information(self, "Success", graph_message)
                self.update_status(f"Graph generated successfully: {os.path.basename(full_path)}", "green")
            else:
                self.log_output(graph_message)
                QMessageBox.critical(self, "Graph Generation Error", graph_message)
                self.update_status("Graph generation failed.", "red")
                self.open_graph_btn.setEnabled(False)
        else:
            self.log_output(f"Parsing failed, cannot generate graph: {parse_error}")
            QMessageBox.critical(self, "Parsing Error", parse_error)
            self.update_status("Parsing failed.", "red")
            self.open_graph_btn.setEnabled(False)

    def open_last_generated_graph(self):
        if not self.last_generated_graph_path or not os.path.exists(self.last_generated_graph_path):
            QMessageBox.warning(self, "Warning", "No graph has been generated or file not found.")
            self.update_status("Error: No generated graph to open.", "red")
            return

        try:
            if sys.platform == "win32":
                os.startfile(self.last_generated_graph_path)
            elif sys.platform == "darwin": # macOS
                subprocess.run(['open', self.last_generated_graph_path])
            else: # Linux and other Unix-like systems
                subprocess.run(['xdg-open', self.last_generated_graph_path])
            self.update_status(f"Opening {os.path.basename(self.last_generated_graph_path)}...", "green")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not open file: {e}")
            self.update_status(f"Error opening graph: {e}", "red")

    def show_about_dialog(self):
        QMessageBox.about(self, "About Python Code Structure Visualizer",
                          "<h2>Python Code Structure Visualizer</h2>"
                          "<p>Version 1.2 (Advanced Analysis)</p>"
                          "<p>Developed by Angelus</p>"
                          "<p>This tool performs a deeper analysis of Python code "
                          "using AST parsing to extract global variables, class attributes, "
                          "detailed function/method signatures, decorators, and function calls. "
                          "It then visualizes the structure with Graphviz.</p>"
                          "<p>Requires Graphviz installed on your system.</p>"
                          "<p><i>Note: Theme setting is stored in system preferences.</i></p>")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = CodeVisualizerApp()
    window.show()
    sys.exit(app.exec())