#!/usr/bin/env python3
"""
OMF Publisher for AVEVA Connect Data Services - V3.04
=====================================================
Publishes APO Analytics data using descriptive stream names
plus pre-computed INSIGHTS that enable AI Assistant to answer
high-level process engineering questions.

V3.04 Changes:
- Added Insights engine that ranks top 10 optimization situations
- Each Insight has a descriptive name and explanation
- AI Assistant can now respond to "show me top 10 situations"
- All insights are self-explanatory for non-specialist stakeholders
"""

import json
import time
import re
import gzip
from datetime import datetime, timezone

import requests


def sanitize_stream_id(name):
    """Convert a .trc variable path to a valid stream ID"""
    clean = name.lstrip("/")
    clean = clean.replace(':', '.')
    clean = clean.replace('/', '.')
    clean = clean.replace('[', '_')
    clean = clean.replace(']', '')
    clean = clean.replace('"', '')
    clean = clean.replace(' ', '_')
    clean = clean.replace('(', '')
    clean = clean.replace(')', '')
    while '..' in clean:
        clean = clean.replace('..', '.')
    return "APO." + clean


def make_friendly_name(var_path):
    """Create a human-friendly name from a variable path"""
    clean = var_path.lstrip("/")
    clean = clean.replace(':', ' ')
    clean = clean.replace('/', ' > ')
    clean = clean.replace('[', ' ')
    clean = clean.replace(']', '')
    clean = clean.replace('"', '')
    return clean


def compute_insights(parsed_data):
    """Compute top 10 ranked insights from parsed optimization data"""
    insights = []

    # --- Insight: Highest Shadow Price (most economically limiting constraint) ---
    if parsed_data["active_constraints"]:
        sorted_constraints = sorted(
            parsed_data["active_constraints"],
            key=lambda x: abs(x["kuhn_tucker"]),
            reverse=True
        )
        top_constraint = sorted_constraints[0]
        insights.append({
            "rank": 1,
            "id": "APO.Insight.Rank01.HighestEconomicBottleneck",
            "name": "#1 BOTTLENECK: " + make_friendly_name(top_constraint["dependent_variable"]) + " is the most economically limiting constraint",
            "description": (
                top_constraint["bound_type"] + " bound on " + top_constraint["dependent_variable"]
                + " has shadow price (Kuhn-Tucker) = " + str(top_constraint["kuhn_tucker"])
                + ". This means relaxing this constraint by 1 unit would improve profit by $"
                + str(abs(top_constraint["kuhn_tucker"])) + ". "
                + "Paired with independent variable: " + top_constraint["independent_variable"]
                + ". RECOMMENDATION: Evaluate increasing capacity or relaxing the limit on "
                + top_constraint["dependent_variable"] + " for maximum economic benefit."
            ),
            "value": abs(top_constraint["kuhn_tucker"])
        })

    # --- Insight: Largest Revenue/Cost Driver ---
    if parsed_data["top_contributors"]:
        sorted_contribs = sorted(
            parsed_data["top_contributors"],
            key=lambda x: abs(x["contribution"]),
            reverse=True
        )
        top_contrib = sorted_contribs[0]
        revenue_or_cost = "REVENUE DRIVER" if top_contrib["dO_dX"] > 0 else "COST DRIVER"
        insights.append({
            "rank": 2,
            "id": "APO.Insight.Rank02.LargestEconomicDriver",
            "name": "#2 ECONOMICS: " + make_friendly_name(top_contrib["variable"]) + " is the largest " + revenue_or_cost,
            "description": (
                top_contrib["variable"] + " has economic contribution = " + str(top_contrib["contribution"])
                + ". This represents the single largest economic factor in the optimization. "
                + "dO/dX = " + str(top_contrib["dO_dX"]) + " (" + ("+1 = revenue stream" if top_contrib["dO_dX"] > 0 else "-1 = cost stream") + "). "
                + "RECOMMENDATION: Any operational change that increases this stream\'s output will have the highest economic impact."
            ),
            "value": abs(top_contrib["contribution"])
        })

    # --- Insight: Most Profitable Variable to Move ---
    if parsed_data["objective_sensitivities"]:
        sorted_obj = sorted(
            parsed_data["objective_sensitivities"],
            key=lambda x: abs(x.get("total_derivative", 0) or 0),
            reverse=True
        )
        top_obj = sorted_obj[0]
        total_deriv = top_obj.get("total_derivative", 0) or 0
        direction = "INCREASE" if total_deriv > 0 else "DECREASE"
        insights.append({
            "rank": 3,
            "id": "APO.Insight.Rank03.MostProfitableMove",
            "name": "#3 OPPORTUNITY: " + direction + " " + make_friendly_name(top_obj["independent_variable"]) + " for maximum profit",
            "description": (
                "Total economic derivative for " + top_obj["independent_variable"] + " = " + str(total_deriv)
                + " $/unit. This means each unit " + direction.lower() + " in this variable improves profit by $"
                + str(abs(total_deriv)) + ". "
                + "This is the most profitable variable to move in the current operating state. "
                + "RECOMMENDATION: " + direction + " " + top_obj["independent_variable"] + " within operational limits."
            ),
            "value": abs(total_deriv)
        })

    # --- Insight: Second most limiting constraint ---
    if len(sorted_constraints) > 1:
        second_constraint = sorted_constraints[1]
        insights.append({
            "rank": 4,
            "id": "APO.Insight.Rank04.SecondBottleneck",
            "name": "#4 BOTTLENECK: " + make_friendly_name(second_constraint["dependent_variable"]) + " is the second most limiting constraint",
            "description": (
                second_constraint["bound_type"] + " bound on " + second_constraint["dependent_variable"]
                + " has shadow price = " + str(second_constraint["kuhn_tucker"])
                + ". Economic impact of relaxation: $" + str(abs(second_constraint["kuhn_tucker"])) + "/unit. "
                + "Independent variable: " + second_constraint["independent_variable"]
                + ". RECOMMENDATION: After addressing Rank #1, this is the next constraint to evaluate."
            ),
            "value": abs(second_constraint["kuhn_tucker"])
        })

    # --- Insight: Tightest Relaxation Limit ---
    if parsed_data["solution_sensitivities"]:
        all_relax = []
        for ss in parsed_data["solution_sensitivities"]:
            for rl in ss.get("relaxation_limits", []):
                if rl > 0:
                    all_relax.append({"constraint": ss["constraint"], "limit": rl})
        if all_relax:
            tightest = min(all_relax, key=lambda x: x["limit"])
            insights.append({
                "rank": 5,
                "id": "APO.Insight.Rank05.TightestConstraint",
                "name": "#5 RISK: " + tightest["constraint"] + " has the smallest margin before active set changes",
                "description": (
                    "Constraint '" + tightest["constraint"] + "' can only be relaxed by "
                    + str(tightest["limit"]) + " units before the optimization active set changes. "
                    + "This is the tightest margin in the system. Small disturbances could cause the optimizer to restructure. "
                    + "RECOMMENDATION: Monitor this constraint closely. Consider adding robustness margin."
                ),
                "value": tightest["limit"]
            })

    # --- Insight: Second largest contributor ---
    if len(sorted_contribs) > 1:
        second_contrib = sorted_contribs[1]
        insights.append({
            "rank": 6,
            "id": "APO.Insight.Rank06.SecondLargestDriver",
            "name": "#6 ECONOMICS: " + make_friendly_name(second_contrib["variable"]) + " is the second largest economic driver",
            "description": (
                second_contrib["variable"] + " contribution = " + str(second_contrib["contribution"])
                + ". Combined with #2, these two streams represent the dominant economics of the process. "
                + "RECOMMENDATION: Focus optimization efforts on maximizing these two revenue/cost streams."
            ),
            "value": abs(second_contrib["contribution"])
        })

    # --- Insight: Least impactful constraint (candidate for removal) ---
    if len(sorted_constraints) > 0:
        least_constraint = sorted_constraints[-1]
        insights.append({
            "rank": 7,
            "id": "APO.Insight.Rank07.LeastImpactfulConstraint",
            "name": "#7 EFFICIENCY: " + make_friendly_name(least_constraint["dependent_variable"]) + " has minimal economic impact",
            "description": (
                least_constraint["bound_type"] + " bound on " + least_constraint["dependent_variable"]
                + " has shadow price = " + str(least_constraint["kuhn_tucker"])
                + ". This constraint barely affects the economic objective (|KT| = " + str(abs(least_constraint["kuhn_tucker"])) + "). "
                + "RECOMMENDATION: This constraint may be overly conservative. Relaxing it would have minimal benefit but also minimal risk."
            ),
            "value": abs(least_constraint["kuhn_tucker"])
        })

    # --- Insight: Power costs significance ---
    if parsed_data["top_contributors"]:
        power_costs = [tc for tc in parsed_data["top_contributors"] if "Power" in tc["variable"]]
        total_power = sum(abs(pc["contribution"]) for pc in power_costs)
        total_all = sum(abs(tc["contribution"]) for tc in parsed_data["top_contributors"])
        pct = (total_power / total_all * 100) if total_all > 0 else 0
        insights.append({
            "rank": 8,
            "id": "APO.Insight.Rank08.PowerCostSignificance",
            "name": "#8 UTILITIES: Power/energy costs represent " + "{:.2f}".format(pct) + "% of total economics",
            "description": (
                "Total power-related costs (Motor1 + C1) = " + "{:.6f}".format(total_power)
                + " vs total economic activity = " + "{:.3f}".format(total_all)
                + ". Power costs are " + "{:.2f}".format(pct) + "% of the economic picture. "
                + ("Power costs are NEGLIGIBLE - focus on feed/product economics instead." if pct < 1 else "Power costs are SIGNIFICANT - energy efficiency improvements could help.")
                + " RECOMMENDATION: " + ("Do not prioritize power reduction projects." if pct < 1 else "Evaluate energy efficiency opportunities.")
            ),
            "value": pct
        })

    # --- Insight: Constraint sensitivities ---
    if parsed_data["constraint_sensitivities"]:
        cs = parsed_data["constraint_sensitivities"][0]
        if cs.get("violated_constraints"):
            max_violation = max(cs["violated_constraints"], key=lambda x: abs(x["dW_dZ"]))
            insights.append({
                "rank": 9,
                "id": "APO.Insight.Rank09.FastestViolation",
                "name": "#9 SENSITIVITY: " + make_friendly_name(max_violation["constraint"]) + " is the fastest reacting constraint",
                "description": (
                    "When moving " + cs["independent_variable"] + " in the profitable direction (" + cs["direction"] + "), "
                    + "constraint " + max_violation["constraint"] + " approaches violation at rate dW/dZ = " + str(max_violation["dW_dZ"])
                    + ". This is the constraint that PREVENTS further profit improvement. "
                    + "RECOMMENDATION: This is the binding constraint that the optimizer fights against. Relaxing it unlocks more profit."
                ),
                "value": abs(max_violation["dW_dZ"])
            })

    # --- Insight: Overall optimization status ---
    if parsed_data["objective_sensitivities"]:
        all_derivs = [abs(os.get("total_derivative", 0) or 0) for os in parsed_data["objective_sensitivities"]]
        max_deriv = max(all_derivs) if all_derivs else 0
        min_deriv = min(all_derivs) if all_derivs else 0
        is_optimal = max_deriv < 1.0
        insights.append({
            "rank": 10,
            "id": "APO.Insight.Rank10.OptimizationStatus",
            "name": "#10 STATUS: Optimization is " + ("WELL CONVERGED" if is_optimal else "SHOWING SIGNIFICANT GRADIENTS - review convergence"),
            "description": (
                "Reduced gradients range from " + "{:.6f}".format(min_deriv) + " to " + "{:.4f}".format(max_deriv)
                + ". " + ("All gradients are small, confirming the solution is at a true optimum within the given constraints." if is_optimal else "Some gradients are large, indicating the optimizer may not have fully converged or there are active constraints preventing optimality.")
                + " Number of active constraints: " + str(len(parsed_data["active_constraints"]))
                + ". Total independent variables with non-zero gradients: " + str(len(parsed_data["objective_sensitivities"]))
                + ". RECOMMENDATION: " + ("Solution is reliable for decision-making." if is_optimal else "Consider re-running with tighter convergence tolerances.")
            ),
            "value": max_deriv
        })

    return insights


class OMFPublisher:
    """Publishes data to AVEVA Connect Data Services via OMF - V3.04"""

    def __init__(self, config):
        self.config = config
        self.resource = config["Resource"].rstrip("/")
        self.tenant = config["Tenant"]
        self.namespace = config["NamespaceId"]
        self.client_id = config["ClientId"]
        self.client_secret = config["ClientSecret"]
        self.api_version = config.get("ApiVersion", "v1")
        self.omf_version = config.get("OmfVersion", "1.2")
        self.verify_ssl = config.get("VerifySSL", True)
        self.use_compression = config.get("UseCompression", False)
        self.timeout = config.get("WebRequestTimeoutSeconds", 30)
        self.access_token = None
        self.token_expiry = 0

    def authenticate(self):
        token_url = self.resource + "/identity/connect/token"
        payload = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "grant_type": "client_credentials"
        }
        response = requests.post(token_url, data=payload, verify=self.verify_ssl, timeout=self.timeout)
        if response.status_code != 200:
            raise Exception("Authentication failed (HTTP " + str(response.status_code) + "): " + response.text)
        token_data = response.json()
        self.access_token = token_data["access_token"]
        self.token_expiry = time.time() + token_data.get("expires_in", 3600) - 60
        return True

    def _ensure_authenticated(self):
        if time.time() >= self.token_expiry:
            self.authenticate()

    def _get_omf_url(self):
        return (self.resource + "/api/" + self.api_version + "/tenants/" + self.tenant + "/namespaces/" + self.namespace + "/omf")

    def _send_omf_message(self, message_type, body):
        self._ensure_authenticated()
        headers = {
            "Authorization": "Bearer " + self.access_token,
            "MessageType": message_type,
            "MessageFormat": "json",
            "OmfVersion": self.omf_version,
            "Action": "create",
            "Content-Type": "application/json"
        }
        body_bytes = json.dumps(body).encode("utf-8")
        if self.use_compression:
            headers["Compression"] = "gzip"
            body_bytes = gzip.compress(body_bytes)
        response = requests.post(self._get_omf_url(), headers=headers, data=body_bytes, verify=self.verify_ssl, timeout=self.timeout)
        if response.status_code not in [200, 202, 204]:
            raise Exception("OMF " + message_type + " message failed (HTTP " + str(response.status_code) + "): " + response.text)
        return response

    def send_types(self):
        """Send PI-Float64 standard type"""
        types = [{
            "id": "PI-Float64",
            "name": "PI-Float64",
            "classification": "dynamic",
            "type": "object",
            "description": "Standard PI Float64 type for Connect Visualization",
            "properties": {
                "Timestamp": {"type": "string", "format": "date-time", "isindex": True},
                "Value": {"type": "number", "name": "Value", "format": "float64"},
                "IsQuestionable": {"type": "boolean"},
                "IsSubstituted": {"type": "boolean"},
                "IsAnnotated": {"type": "boolean"},
                "SystemStateCode": {"type": "integer"},
                "DigitalStateName": {"type": "string"}
            }
        }]
        self._send_omf_message("type", types)

    def send_containers(self, parsed_data):
        """Send containers: process variables + insights"""
        containers = []

        # --- Active Constraints ---
        for ac in parsed_data["active_constraints"]:
            dep_var = ac["dependent_variable"]
            ind_var = ac["independent_variable"]
            bound = ac["bound_type"]
            base_id = sanitize_stream_id(dep_var)
            ind_id = sanitize_stream_id(ind_var)
            containers.append({"id": base_id + ".ShadowPrice", "typeid": "PI-Float64", "name": make_friendly_name(dep_var) + " - Shadow Price (Kuhn-Tucker)", "description": bound + " bound constraint on " + dep_var + ". Shadow price = economic value of relaxing this constraint by 1 unit. Paired with: " + ind_var})
            containers.append({"id": base_id + ".Derivative", "typeid": "PI-Float64", "name": make_friendly_name(dep_var) + " - Constraint Derivative (dW/dZ)", "description": "Rate of change of " + dep_var + " with respect to " + ind_var})
            containers.append({"id": ind_id + ".ObjectiveGradient", "typeid": "PI-Float64", "name": make_friendly_name(ind_var) + " - Objective Function Gradient (dO/dZ)", "description": "Economic sensitivity: profit change per unit change in " + ind_var})

        # --- Solution Sensitivities ---
        for ss in parsed_data["solution_sensitivities"]:
            constraint = ss["constraint"]
            constraint_id = sanitize_stream_id(constraint)
            for vs in ss.get("variable_sensitivities", []):
                var_name = vs["variable"]
                var_id = sanitize_stream_id(var_name)
                stream_id = constraint_id + ".SensTo." + var_id.replace("APO.", "")
                containers.append({"id": stream_id, "typeid": "PI-Float64", "name": "Sensitivity of " + make_friendly_name(var_name) + " to relaxation of " + constraint, "description": "If constraint relaxed by 1 unit, this variable changes by this amount"})
            for k, rl in enumerate(ss.get("relaxation_limits", []), 1):
                stream_id = constraint_id + ".RelaxationLimit" + str(k)
                containers.append({"id": stream_id, "typeid": "PI-Float64", "name": constraint + " - Relaxation Limit " + str(k), "description": "How much this constraint can be relaxed before active set changes"})

        # --- Objective Function Sensitivities ---
        for obj_sens in parsed_data["objective_sensitivities"]:
            ind_var = obj_sens["independent_variable"]
            ind_id = sanitize_stream_id(ind_var)
            for contrib in obj_sens.get("contributions", []):
                contrib_var = contrib["variable"]
                contrib_id = sanitize_stream_id(contrib_var)
                base = ind_id + ".EconImpactOn." + contrib_id.replace("APO.", "")
                containers.append({"id": base + ".Product", "typeid": "PI-Float64", "name": "Economic impact of " + make_friendly_name(ind_var) + " on " + make_friendly_name(contrib_var), "description": "Net economic effect (dO/dX * dX/dZ). Positive = increases revenue, Negative = increases cost"})
            containers.append({"id": ind_id + ".TotalEconomicDerivative", "typeid": "PI-Float64", "name": "Total Economic Derivative of " + make_friendly_name(ind_var), "description": "Total profit change per unit change. Sum of all contributions. Equals reduced gradient at optimum"})

        # --- Constraint Sensitivities ---
        for i, cs in enumerate(parsed_data["constraint_sensitivities"], 1):
            ind_var = cs["independent_variable"]
            ind_id = sanitize_stream_id(ind_var)
            containers.append({"id": ind_id + ".OptimalDirectionGradient", "typeid": "PI-Float64", "name": make_friendly_name(ind_var) + " - Optimal Direction Gradient", "description": "Objective gradient. A " + cs["direction"] + " improves profit. Shows how profitable it would be to move if unconstrained"})
            for vc in cs.get("violated_constraints", []):
                con_name = vc["constraint"]
                con_id = sanitize_stream_id(con_name)
                containers.append({"id": ind_id + ".ViolationRateOn." + con_id.replace("APO.", "") + ".dW_dZ", "typeid": "PI-Float64", "name": "Rate " + make_friendly_name(ind_var) + " violates " + make_friendly_name(con_name), "description": "How fast constraint approaches violation when variable moves in optimal direction. Higher = tighter"})

        # --- Top Contributors ---
        for tc in parsed_data["top_contributors"]:
            var_name = tc["variable"]
            var_id = sanitize_stream_id(var_name)
            containers.append({"id": var_id + ".EconomicContribution", "typeid": "PI-Float64", "name": make_friendly_name(var_name) + " - Economic Contribution (Rank #" + str(tc["rank"]) + ")", "description": "Rank #" + str(tc["rank"]) + " contributor. Negative = cost stream. Positive = revenue stream. Total cash flow impact on objective"})

        # --- INSIGHTS (Top 10 pre-computed) ---
        insights = compute_insights(parsed_data)
        for insight in insights:
            containers.append({
                "id": insight["id"],
                "typeid": "PI-Float64",
                "name": insight["name"],
                "description": insight["description"]
            })

        self._send_omf_message("container", containers)
        return insights

    def send_data(self, parsed_data, insights=None):
        """Send data values with PI-Float64 format"""
        now = datetime.now(timezone.utc)
        all_data = []

        def add_value(container_id, timestamp, value):
            all_data.append({"containerid": container_id, "values": [
                {"Timestamp": timestamp, "Value": float(value), "IsQuestionable": False, "IsSubstituted": False, "IsAnnotated": False}
            ]})

        # --- Active Constraints ---
        for ac in parsed_data["active_constraints"]:
            dep_var = ac["dependent_variable"]
            ind_var = ac["independent_variable"]
            ts = ac.get("timestamp", now.isoformat())
            base_id = sanitize_stream_id(dep_var)
            ind_id = sanitize_stream_id(ind_var)
            add_value(base_id + ".ShadowPrice", ts, ac["kuhn_tucker"])
            add_value(base_id + ".Derivative", ts, ac["derivative"])
            add_value(ind_id + ".ObjectiveGradient", ts, ac["dO_dZ"])

        # --- Solution Sensitivities ---
        for ss in parsed_data["solution_sensitivities"]:
            constraint = ss["constraint"]
            constraint_id = sanitize_stream_id(constraint)
            ts = ss.get("timestamp", now.isoformat())
            for vs in ss.get("variable_sensitivities", []):
                var_name = vs["variable"]
                var_id = sanitize_stream_id(var_name)
                stream_id = constraint_id + ".SensTo." + var_id.replace("APO.", "")
                add_value(stream_id, ts, vs["sensitivity_value"])
            for k, rl in enumerate(ss.get("relaxation_limits", []), 1):
                stream_id = constraint_id + ".RelaxationLimit" + str(k)
                add_value(stream_id, ts, rl)

        # --- Objective Function Sensitivities ---
        for obj_sens in parsed_data["objective_sensitivities"]:
            ind_var = obj_sens["independent_variable"]
            ind_id = sanitize_stream_id(ind_var)
            ts = obj_sens.get("timestamp", now.isoformat())
            for contrib in obj_sens.get("contributions", []):
                contrib_var = contrib["variable"]
                contrib_id = sanitize_stream_id(contrib_var)
                base = ind_id + ".EconImpactOn." + contrib_id.replace("APO.", "")
                add_value(base + ".Product", ts, contrib["product"])
            total_deriv = float(obj_sens.get("total_derivative", 0.0) or 0.0)
            add_value(ind_id + ".TotalEconomicDerivative", ts, total_deriv)

        # --- Constraint Sensitivities ---
        for i, cs in enumerate(parsed_data["constraint_sensitivities"], 1):
            ind_var = cs["independent_variable"]
            ind_id = sanitize_stream_id(ind_var)
            ts = cs.get("timestamp", now.isoformat())
            obj_grad = float(cs.get("objective_gradient", 0.0) or 0.0)
            add_value(ind_id + ".OptimalDirectionGradient", ts, obj_grad)
            for vc in cs.get("violated_constraints", []):
                con_name = vc["constraint"]
                con_id = sanitize_stream_id(con_name)
                stream_id = ind_id + ".ViolationRateOn." + con_id.replace("APO.", "") + ".dW_dZ"
                add_value(stream_id, ts, vc["dW_dZ"])

        # --- Top Contributors ---
        for tc in parsed_data["top_contributors"]:
            var_name = tc["variable"]
            var_id = sanitize_stream_id(var_name)
            ts = tc.get("timestamp", now.isoformat())
            add_value(var_id + ".EconomicContribution", ts, tc["contribution"])

        # --- INSIGHTS ---
        if insights:
            for insight in insights:
                add_value(insight["id"], now.isoformat(), insight["value"])

        # Send in batches
        batch_size = 100
        for i in range(0, len(all_data), batch_size):
            batch = all_data[i:i + batch_size]
            self._send_omf_message("data", batch)


if __name__ == "__main__":
    print("This module is not meant to be run directly. Use program.py or app_gui.py instead.")
