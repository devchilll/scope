"""Compliance-specific logging for regulatory requirements.

This module provides specialized logging for PCI-DSS, SOC2, and other
regulatory compliance requirements.
"""

import logging
from datetime import datetime
from typing import Optional, Dict, Any
from pathlib import Path
import json


class ComplianceLogger:
    """Logger for regulatory compliance (PCI-DSS, SOC2, etc.)."""
    
    def __init__(self, log_dir: Optional[str] = None):
        """Initialize compliance logger.
        
        Args:
            log_dir: Directory for compliance logs. If None, uses default location.
        """
        if log_dir is None:
            log_dir = Path(__file__).parent / "compliance_logs"
        else:
            log_dir = Path(log_dir)
        
        log_dir.mkdir(exist_ok=True)
        self.log_dir = log_dir
        
        # Create separate log files for different compliance frameworks
        today = datetime.now().strftime("%Y-%m-%d")
        
        # PCI-DSS log (Payment Card Industry Data Security Standard)
        self.pci_logger = self._create_logger(
            "prime.compliance.pci",
            log_dir / f"pci_dss_{today}.jsonl"
        )
        
        # SOC2 log (Service Organization Control 2)
        self.soc2_logger = self._create_logger(
            "prime.compliance.soc2",
            log_dir / f"soc2_{today}.jsonl"
        )
        
        # General compliance log
        self.general_logger = self._create_logger(
            "prime.compliance.general",
            log_dir / f"compliance_{today}.jsonl"
        )
    
    def _create_logger(self, name: str, log_file: Path) -> logging.Logger:
        """Create a logger with file handler.
        
        Args:
            name: Logger name
            log_file: Log file path
            
        Returns:
            Configured logger
        """
        logger = logging.getLogger(name)
        logger.setLevel(logging.INFO)
        
        handler = logging.FileHandler(log_file)
        handler.setLevel(logging.INFO)
        logger.addHandler(handler)
        
        return logger
    
    def _log_event(
        self,
        logger: logging.Logger,
        event_type: str,
        user_id: str,
        details: Dict[str, Any]
    ):
        """Log a compliance event.
        
        Args:
            logger: Logger to use
            event_type: Type of compliance event
            user_id: User ID
            details: Event details
        """
        event = {
            "timestamp": datetime.now().isoformat(),
            "event_type": event_type,
            "user_id": user_id,
            "details": details
        }
        logger.info(json.dumps(event))
    
    # PCI-DSS Logging
    
    def log_pci_data_access(
        self,
        user_id: str,
        data_type: str,
        account_id: str,
        operation: str
    ):
        """Log access to PCI-protected data.
        
        PCI-DSS Requirement 10.2: Implement automated audit trails
        
        Args:
            user_id: User accessing the data
            data_type: Type of data (account, transaction, etc.)
            account_id: Account ID
            operation: Operation performed (read, write, delete)
        """
        self._log_event(
            self.pci_logger,
            "pci_data_access",
            user_id,
            {
                "data_type": data_type,
                "account_id": account_id,
                "operation": operation,
                "requirement": "PCI-DSS 10.2"
            }
        )
    
    def log_pci_authentication(
        self,
        user_id: str,
        success: bool,
        method: str,
        ip_address: Optional[str] = None
    ):
        """Log authentication attempt.
        
        PCI-DSS Requirement 10.2.4: Invalid logical access attempts
        
        Args:
            user_id: User attempting authentication
            success: Whether authentication succeeded
            method: Authentication method used
            ip_address: IP address of the request
        """
        self._log_event(
            self.pci_logger,
            "pci_authentication",
            user_id,
            {
                "success": success,
                "method": method,
                "ip_address": ip_address,
                "requirement": "PCI-DSS 10.2.4"
            }
        )
    
    def log_pci_privileged_action(
        self,
        user_id: str,
        action: str,
        target: str,
        result: str
    ):
        """Log privileged administrative action.
        
        PCI-DSS Requirement 10.2.2: Actions by privileged users
        
        Args:
            user_id: Admin user ID
            action: Action performed
            target: Target of the action
            result: Result of the action
        """
        self._log_event(
            self.pci_logger,
            "pci_privileged_action",
            user_id,
            {
                "action": action,
                "target": target,
                "result": result,
                "requirement": "PCI-DSS 10.2.2"
            }
        )
    
    # SOC2 Logging
    
    def log_soc2_access_control(
        self,
        user_id: str,
        resource: str,
        permission: str,
        granted: bool
    ):
        """Log access control decision.
        
        SOC2 CC6.1: Logical and physical access controls
        
        Args:
            user_id: User requesting access
            resource: Resource being accessed
            permission: Permission required
            granted: Whether access was granted
        """
        self._log_event(
            self.soc2_logger,
            "soc2_access_control",
            user_id,
            {
                "resource": resource,
                "permission": permission,
                "granted": granted,
                "control": "SOC2 CC6.1"
            }
        )
    
    def log_soc2_data_processing(
        self,
        user_id: str,
        data_type: str,
        operation: str,
        purpose: str
    ):
        """Log data processing activity.
        
        SOC2 CC6.7: Data classification and handling
        
        Args:
            user_id: User processing data
            data_type: Type of data
            operation: Operation performed
            purpose: Business purpose
        """
        self._log_event(
            self.soc2_logger,
            "soc2_data_processing",
            user_id,
            {
                "data_type": data_type,
                "operation": operation,
                "purpose": purpose,
                "control": "SOC2 CC6.7"
            }
        )
    
    def log_soc2_incident(
        self,
        user_id: str,
        incident_type: str,
        severity: str,
        description: str
    ):
        """Log security incident.
        
        SOC2 CC7.3: Incident response
        
        Args:
            user_id: User reporting or involved in incident
            incident_type: Type of incident
            severity: Severity level
            description: Incident description
        """
        self._log_event(
            self.soc2_logger,
            "soc2_incident",
            user_id,
            {
                "incident_type": incident_type,
                "severity": severity,
                "description": description,
                "control": "SOC2 CC7.3"
            }
        )
    
    # General Compliance
    
    def log_data_retention(
        self,
        data_type: str,
        action: str,
        record_count: int
    ):
        """Log data retention action.
        
        Args:
            data_type: Type of data
            action: Action (archive, delete, etc.)
            record_count: Number of records affected
        """
        self._log_event(
            self.general_logger,
            "data_retention",
            "system",
            {
                "data_type": data_type,
                "action": action,
                "record_count": record_count
            }
        )


# Global compliance logger instance
_compliance_logger: Optional[ComplianceLogger] = None


def get_compliance_logger() -> ComplianceLogger:
    """Get the global compliance logger instance."""
    global _compliance_logger
    if _compliance_logger is None:
        _compliance_logger = ComplianceLogger()
    return _compliance_logger
