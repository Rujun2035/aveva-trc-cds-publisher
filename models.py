#!/usr/bin/env python3
"""
Data Models for TRC Parser
==========================
Defines the data structures used throughout the application.
These correspond to the OMF Types published to CDS.
"""

from dataclasses import dataclass, field
from typing import List, Optional
from datetime import datetime


@dataclass
class ActiveConstraintType:
    """Represents an active constraint - independent variable pairing.
    
    Physical meaning:
    - The dependent variable has hit its bound (mass/energy conservation limit)
    - The Kuhn-Tucker multiplier shows how much the objective would improve
      if the constraint were relaxed (shadow price)
    - dO/dZ shows the objective function sensitivity
    """
    index: int
    bound_type: str  # "Upper" or "Lower"
    dependent_variable: str
    kuhn_tucker: float
    independent_variable: str
    derivative: float
    dO_dZ: float
    timestamp: str = ""


@dataclass
class SensitivityType:
    """Represents solution sensitivity to an active constraint.
    
    Physical meaning:
    - Shows how much each independent variable would change if the
      constraint were relaxed by one unit
    - Relaxation limits show how far the constraint can be relaxed
      before the active set changes
    """
    constraint: str
    variable: str
    sensitivity_value: float
    relaxation_limit: float
    timestamp: str = ""


@dataclass
class ObjectiveSensitivityContribution:
    """Individual contribution to objective function sensitivity.
    
    Physical meaning:
    - dO/dX: How the objective changes with the contributing variable
    - dX/dZ: How the contributing variable changes with the independent
    - Product: Net effect on objective (dO/dX * dX/dZ)
    """
    variable: str
    dO_dX: float
    dX_dZ: float
    product: float


@dataclass
class ObjectiveSensitivityType:
    """Represents objective function sensitivity to an independent variable.
    
    Physical meaning:
    - Breaks down the total economic effect into individual stream
      contributions (gas revenue, NGL revenue, power costs, etc.)
    - Total derivative should equal the reduced gradient
    """
    index: int
    independent_variable: str
    contributions: List[ObjectiveSensitivityContribution] = field(default_factory=list)
    total_derivative: Optional[float] = None
    timestamp: str = ""


@dataclass
class ViolatedConstraint:
    """A constraint that would be violated by variable movement."""
    bound_type: str
    constraint: str
    kuhn_tucker: float
    dW_dZ: float


@dataclass
class ConstraintSensitivityType:
    """Represents how constraints respond to variable changes.
    
    Physical meaning:
    - Shows which mass/energy conservation constraints would be
      violated if a variable moves in the direction of improving
      the objective
    - dW/dZ shows the rate at which the constraint approaches violation
    """
    direction: str  # "decrease" or "increase"
    independent_variable: str
    objective_gradient: Optional[float] = None
    violated_constraints: List[ViolatedConstraint] = field(default_factory=list)
    timestamp: str = ""


@dataclass
class TopContributorType:
    """Represents a top contributor to the economic objective.
    
    Physical meaning:
    - Ranks the streams/utilities by their economic contribution
    - NGL sink (product revenue) typically dominates
    - Negative contributions represent costs (feed gas, power, refrigerant)
    """
    rank: int
    variable: str
    dO_dX: float
    contribution: float
    timestamp: str = ""
