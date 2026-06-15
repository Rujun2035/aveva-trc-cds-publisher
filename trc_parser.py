#!/usr/bin/env python3
"""
TRC File Parser
===============
Parses AVEVA Process Simulation .trc trace files containing
post-solution analysis data from NLP optimization.

Extracts:
- Active Constraint - Independent Variable Pairings
- Solution Sensitivity to Active Constraints
- Objective Function Sensitivities
- Active Constraint Sensitivities to Independent Variables
- Top Contributors
"""

import re
from datetime import datetime, timezone


class TRCParser:
    """Parser for AVEVA Process Simulation .trc trace files"""

    def __init__(self):
        self.data = {
            "active_constraints": [],
            "solution_sensitivities": [],
            "objective_sensitivities": [],
            "constraint_sensitivities": [],
            "top_contributors": [],
            "metadata": {}
        }

    def parse_file(self, filepath):
        """Parse a .trc file and return structured data"""
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()

        self.data["metadata"] = {
            "source_file": filepath,
            "parse_timestamp": datetime.now(timezone.utc).isoformat(),
            "file_type": "POST-SOLUTION ANALYSIS"
        }

        self._parse_active_constraints(content)
        self._parse_solution_sensitivities(content)
        self._parse_objective_sensitivities(content)
        self._parse_constraint_sensitivities(content)
        self._parse_top_contributors(content)

        return self.data

    def _parse_active_constraints(self, content):
        """Parse Active Constraint - Independent Variable Pairings section"""
        section_pattern = r"Active Constraint - Independent Variable Pairings\n={2,}\n(.+?)(?=Solution Sensitivity|$)"
        match = re.search(section_pattern, content, re.DOTALL)
        if not match:
            return

        section = match.group(1)
        pair_pattern = r"\s*(\d+)\.\s+(Upper|Lower)\s+(\S+)\s+([\-+]?\d+\.\d+E[\-+]?\d+)\s*\n\s+and\s+(\S+)\s+([\-+]?\d+\.\d+E[\-+]?\d+)\s+([\-+]?\d+\.\d+E[\-+]?\d+)"
        
        for match in re.finditer(pair_pattern, section):
            self.data["active_constraints"].append({
                "index": int(match.group(1)),
                "bound_type": match.group(2),
                "dependent_variable": match.group(3),
                "kuhn_tucker": float(match.group(4)),
                "independent_variable": match.group(5),
                "derivative": float(match.group(6)),
                "dO_dZ": float(match.group(7)),
                "timestamp": datetime.now(timezone.utc).isoformat()
            })

    def _parse_solution_sensitivities(self, content):
        """Parse Solution Sensitivity to Active Constraints section"""
        section_pattern = r"Solution Sensitivity to Active Constraints\n={2,}\n(.+?)(?=Objective Function Sensitivities|$)"
        match = re.search(section_pattern, content, re.DOTALL)
        if not match:
            return

        section = match.group(1)
        constraint_blocks = re.split(r"The sensitivity of the solution \(independent variables\)\nto the relaxation of the active constraint:", section)
        
        for block in constraint_blocks[1:]:
            lines = block.strip().split('\n')
            constraint_name = ""
            sensitivities = []
            relaxation_info = []
            
            for line in lines:
                stripped = line.strip()
                if stripped and not stripped.startswith('is as follows'):
                    if not constraint_name:
                        constraint_name = stripped
                        continue
                break
            
            var_pattern = r"\s+(\S+)\s+([\-+]?\d+\.\d+E[\-+]?\d+)"
            relaxation_pattern = r"It could be relaxed by\s+([\-+]?\d+\.\d+E[\-+]?\d+)\s+before"
            
            for line in lines:
                var_match = re.match(var_pattern, line)
                if var_match and 'relaxed' not in line and 'active' not in line.lower():
                    sensitivities.append({
                        "variable": var_match.group(1),
                        "sensitivity_value": float(var_match.group(2))
                    })
                
                relax_match = re.search(relaxation_pattern, line)
                if relax_match:
                    relaxation_info.append(float(relax_match.group(1)))
            
            if constraint_name:
                self.data["solution_sensitivities"].append({
                    "constraint": constraint_name,
                    "variable_sensitivities": sensitivities,
                    "relaxation_limits": relaxation_info,
                    "timestamp": datetime.now(timezone.utc).isoformat()
                })

    def _parse_objective_sensitivities(self, content):
        """Parse Objective Function Sensitivities to Independent Variables"""
        section_pattern = r"Objective Function Sensitivities to Independent Variables\n={2,}\n(.+?)(?=Top Ten Contributors|Active Constraint Sensitivities to Independent Variables|$)"
        match = re.search(section_pattern, content, re.DOTALL)
        if not match:
            return

        section = match.group(1)
        var_headers = re.findall(r"\s+(\d+)\s+(\S+(?:\s+\(Swapped with \S+\))?)", section)
        var_blocks = re.split(r"\s+\d+\s+", section)
        
        for i, (idx, var_name) in enumerate(var_headers):
            contributions = []
            total_derivative = None
            
            if i + 1 < len(var_blocks):
                block = var_blocks[i + 1]
                contrib_pattern = r"(\S+)\s+([\-+]?\d+\.\d+E[\-+]?\d+)\s+([\-+]?\d+\.\d+E[\-+]?\d+)\s+([\-+]?\d+\.\d+E[\-+]?\d+)"
                for match_c in re.finditer(contrib_pattern, block):
                    contributions.append({
                        "variable": match_c.group(1),
                        "dO_dX": float(match_c.group(2)),
                        "dX_dZ": float(match_c.group(3)),
                        "product": float(match_c.group(4))
                    })
                
                total_pattern = r"Total Derivative\s+([\-+]?\d+\.\d+E[\-+]?\d+)"
                total_match = re.search(total_pattern, block)
                if total_match:
                    total_derivative = float(total_match.group(1))
            
            self.data["objective_sensitivities"].append({
                "index": int(idx),
                "independent_variable": var_name.strip(),
                "contributions": contributions,
                "total_derivative": total_derivative,
                "timestamp": datetime.now(timezone.utc).isoformat()
            })

    def _parse_constraint_sensitivities(self, content):
        """Parse Active Constraint Sensitivities to Independent Variables"""
        section_pattern = r"Active Constraint Sensitivities to Independent Variables\n={2,}\n(.+?)$"
        match = re.search(section_pattern, content, re.DOTALL)
        if not match:
            return

        section = match.group(1)
        blocks = re.split(r"\d+\.\s+A (decrease|increase) in the independent variable", section)
        directions = re.findall(r"\d+\.\s+A (decrease|increase) in the independent variable", section)
        
        for i, direction in enumerate(directions):
            if i + 1 >= len(blocks):
                break
            block = blocks[i + 1]
            lines = block.strip().split('\n')
            
            var_name = ""
            gradient_value = None
            violated_constraints = []
            
            grad_pattern = r"with objective function gradient value\s+([\-+]?\d+\.\d+E[\-+]?\d+)"
            constraint_pattern = r"(Upper|Lower)\s+(\S+)\s+([\-+]?\d+\.\d+E[\-+]?\d+)\s+([\-+]?\d+\.\d+E[\-+]?\d+)"
            
            for line in lines:
                if not var_name:
                    vm = re.match(r"\s*\d*\s*(/\S+)", line)
                    if vm:
                        var_name = vm.group(1)
                
                gm = re.search(grad_pattern, line)
                if gm:
                    gradient_value = float(gm.group(1))
                
                cm = re.search(constraint_pattern, line)
                if cm:
                    violated_constraints.append({
                        "bound_type": cm.group(1),
                        "constraint": cm.group(2),
                        "kuhn_tucker": float(cm.group(3)),
                        "dW_dZ": float(cm.group(4))
                    })
            
            if var_name:
                self.data["constraint_sensitivities"].append({
                    "direction": direction,
                    "independent_variable": var_name,
                    "objective_gradient": gradient_value,
                    "violated_constraints": violated_constraints,
                    "timestamp": datetime.now(timezone.utc).isoformat()
                })

    def _parse_top_contributors(self, content):
        """Parse Top Ten Contributors section"""
        section_pattern = r"Top Ten Contributors.*?\n-{2,}.*?\n(.+?)(?=Active Constraint Sensitivities|$)"
        match = re.search(section_pattern, content, re.DOTALL)
        if not match:
            return

        section = match.group(1)
        contrib_pattern = r"(\S+)\s+([\-+]?\d+\.\d+E[\-+]?\d+)\s+([\-+]?\d+\.\d+E[\-+]?\d+)"
        
        rank = 1
        for match_c in re.finditer(contrib_pattern, section):
            self.data["top_contributors"].append({
                "rank": rank,
                "variable": match_c.group(1),
                "dO_dX": float(match_c.group(2)),
                "contribution": float(match_c.group(3)),
                "timestamp": datetime.now(timezone.utc).isoformat()
            })
            rank += 1


if __name__ == "__main__":
    import json
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python trc_parser.py <file.trc>")
        sys.exit(1)
    
    parser = TRCParser()
    data = parser.parse_file(sys.argv[1])
    print(json.dumps(data, indent=2, default=str))
