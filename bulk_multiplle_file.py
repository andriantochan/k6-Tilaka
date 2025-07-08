#!/usr/bin/env python3
"""
Document Signing Performance Test Script
Converted from k6 to Python with enhanced features:
- Structured timing records
- Retry mechanism with exponential backoff
- Comprehensive logging
- Multiple output formats (JSON, CSV)
"""

import json
import csv
import time
import logging
import requests
import random
import string
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field, asdict
from functools import wraps
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('execution.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


@dataclass
class SigningTestConfig:
    """Configuration for the signing test"""
    # API URLs
    access_token_url: str = "https://stg-api.tilaka.id/auth"
    upload_url: str = "https://stg-api.tilaka.id/plus-upload"
    request_sign_url: str = "https://stg-api.tilaka.id/plus-requestsign"
    auth_hash_url: str = "https://stg-api.tilaka.id/signing-authhashsign"
    execute_sign_url: str = "https://stg-api.tilaka.id/plus-executesign"
    check_sign_status_url: str = "https://stg-api.tilaka.id/plus-checksignstatus"
    
    # Credentials
    client_id: str = "37e3cb48-affe-4c35-904a-f4ed7a24fcd6"
    client_secret: str = "a9a1e30f-91fa-44aa-be27-7e84452bb423"
    company_id: str = "11111111-1111-1111-1111-111111111111"
    
    # User credentials
    username: str = "andriregstg386"
    password: str = "Password123#"
    otp_pin: str = "985070"
    
    # Test parameters
    number_of_uploads: int = 15
    sign_per_doc: int = 1
    pdf_file_path: str = "./10-pg-blank.pdf"
    
    # Signature parameters
    coord_x: int = 0
    coord_y: int = 0
    width: int = 200
    height: int = 100
    page_number: int = 1
    signature_image: str = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
    
    # Retry configuration
    max_retries: int = 3
    retry_backoff_factor: float = 1.0
    request_timeout: int = 30
    
    # Polling configuration
    status_check_interval: int = 1
    max_status_checks: int = 300  # 5 minutes max


@dataclass
class SigningTestState:
    """Mutable state during test execution"""
    access_token: str = ""
    user_token: str = ""
    uploaded_files: List[str] = field(default_factory=list)
    request_id: str = ""
    user_identifier: str = ""
    id_rsa: str = ""


@dataclass
class TimingResult:
    """Record for timing measurements"""
    operation: str
    start_time: float
    end_time: float
    duration: float
    status: str
    details: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def start_time_formatted(self) -> str:
        return format_timestamp(self.start_time * 1000)
    
    @property
    def end_time_formatted(self) -> str:
        return format_timestamp(self.end_time * 1000)


class ResponseLogger:
    """Logger for API responses"""
    def __init__(self):
        self.responses: List[Dict[str, Any]] = []
    
    def log_response(self, operation: str, url: str, status_code: int, 
                    response_body: Any, request_body: Optional[Any] = None):
        """Log API response"""
        entry = {
            "timestamp": datetime.now().isoformat(),
            "operation": operation,
            "url": url,
            "status_code": status_code,
            "request_body": request_body,
            "response_body": response_body
        }
        self.responses.append(entry)
        
    def save_to_file(self, filename: str = "response_bodies.json"):
        """Save all responses to file"""
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(self.responses, f, indent=2, ensure_ascii=False)
        logger.info(f"Response bodies saved to {filename}")


class SigningPerformanceTest:
    def __init__(self, config: SigningTestConfig):
        self.config = config
        self.state = SigningTestState()
        self.timings: List[TimingResult] = []
        self.response_logger = ResponseLogger()
        self.session = self._create_session()
        
    def _create_session(self) -> requests.Session:
        """Create requests session with retry logic"""
        session = requests.Session()
        retry_strategy = Retry(
            total=self.config.max_retries,
            backoff_factor=self.config.retry_backoff_factor,
            status_forcelist=[500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "PUT", "DELETE", "OPTIONS", "TRACE", "POST"]
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        return session
    
    def retry_on_401(self, func):
        """Decorator to retry on 401 with token refresh"""
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 401:
                    logger.warning("Got 401, refreshing token and retrying...")
                    self._get_access_token()
                    return func(*args, **kwargs)
                raise
        return wrapper
    
    def _record_timing(self, operation: str, func, *args, **kwargs):
        """Execute function and record timing"""
        start_time = time.time()
        logger.info(f"---- {operation} start from {format_timestamp(start_time * 1000)}")
        
        try:
            result = func(*args, **kwargs)
            status = "SUCCESS"
        except Exception as e:
            logger.error(f"Error in {operation}: {str(e)}")
            status = "FAILED"
            result = None
            raise
        finally:
            end_time = time.time()
            duration = end_time - start_time
            
            logger.info(f"---- {operation} end at {format_timestamp(end_time * 1000)}")
            logger.info(f"---- Time taken for {operation}: {duration:.3f} seconds")
            
            timing = TimingResult(
                operation=operation,
                start_time=start_time,
                end_time=end_time,
                duration=duration,
                status=status
            )
            self.timings.append(timing)
        
        return result
    
    def _make_request(self, method: str, url: str, **kwargs) -> requests.Response:
        """Make HTTP request with timeout"""
        kwargs.setdefault('timeout', self.config.request_timeout)
        response = self.session.request(method, url, **kwargs)
        response.raise_for_status()
        return response
    
    @staticmethod
    def generate_random_id(length: int) -> str:
        """Generate random alphanumeric ID"""
        return ''.join(random.choices(string.ascii_lowercase + string.digits, k=length))
    
    def _get_access_token(self) -> str:
        """Get JWT access token"""
        data = {
            "client_id": self.config.client_id,
            "client_secret": self.config.client_secret,
            "grant_type": "client_credentials"
        }
        
        response = self._make_request("POST", self.config.access_token_url, data=data)
        self.response_logger.log_response(
            "Get Access Token", 
            self.config.access_token_url, 
            response.status_code,
            response.json(),
            data
        )
        
        self.state.access_token = response.json()["access_token"]
        return self.state.access_token
    
    def _upload_file(self, file_index: int) -> Tuple[str, float]:
        """Upload single file and return filename and duration"""
        start_time = time.time()
        
        with open(self.config.pdf_file_path, 'rb') as f:
            files = {'file': ('10-pg-blank.pdf', f, 'application/pdf')}
            headers = {'Authorization': f'Bearer {self.state.access_token}'}
            
            response = self.retry_on_401(
                lambda: self._make_request("POST", self.config.upload_url, files=files, headers=headers)
            )()
            
            self.response_logger.log_response(
                f"Upload File {file_index + 1}",
                self.config.upload_url,
                response.status_code,
                response.json()
            )
            
            duration = time.time() - start_time
            return response.json()["filename"], duration
    
    def _create_json_payload(self) -> Dict[str, Any]:
        """Create JSON payload for signing request"""
        json_data = {
            "request_id": self.state.request_id,
            "signatures": [
                {
                    "user_identifier": self.state.user_identifier,
                    "signature_image": self.config.signature_image,
                    "sequence": 1,
                }
            ],
            "list_pdf": []
        }
        
        # Create list_pdf entries
        for filename in self.state.uploaded_files:
            pdf_entry = {
                "filename": filename,
                "signatures": []
            }
            
            # Add signatures based on sign_per_doc
            for j in range(self.config.sign_per_doc):
                pdf_entry["signatures"].append({
                    "user_identifier": self.state.user_identifier,
                    "width": self.config.width,
                    "height": self.config.height,
                    "coordinate_x": self.config.coord_x,
                    "coordinate_y": self.config.coord_y,
                    "page_number": self.config.page_number,
                })
            
            json_data["list_pdf"].append(pdf_entry)
        
        return json_data
    
    def run(self):
        """Run the complete signing test"""
        # Initialize test
        self.state.request_id = self.generate_random_id(6)
        self.state.user_identifier = self.config.username
        
        logger.info(f"Starting test with request_id: {self.state.request_id}")
        
        try:
            # Step 1: Get JWT token
            self._record_timing("Get JWT Token", self._execute_get_token)
            
            # Step 2: Upload files
            self._record_timing("Upload Files", self._execute_upload_files)
            
            # Step 3: Request signing
            self._record_timing("Request Sign", self._execute_request_signing)
            
            # Step 4: Get user token
            self._record_timing("Get User Token", self._execute_get_user_token)
            
            # Step 5: Auth with OTP
            self._record_timing("Auth using OTP", self._execute_auth_otp)
            
            # Step 6: Execute signing
            self._record_timing("Execute Sign", self._execute_signing)
            
            # Step 7: Check signing status
            self._record_timing("Check Sign Status", self._execute_check_status)
            
            # Save results
            self._save_results()
            
        except Exception as e:
            logger.error(f"Test failed: {str(e)}")
            raise
        finally:
            # Always save what we have
            self.response_logger.save_to_file()
    
    def _execute_get_token(self):
        """Execute token retrieval"""
        self._get_access_token()
        time.sleep(1)
    
    def _execute_upload_files(self):
        """Execute file uploads"""
        upload_timings = []
        
        for i in range(self.config.number_of_uploads):
            try:
                filename, duration = self._upload_file(i)
                self.state.uploaded_files.append(filename)
                
                # Record individual upload timing
                upload_timing = TimingResult(
                    operation=f"Upload File {i + 1}",
                    start_time=time.time() - duration,
                    end_time=time.time(),
                    duration=duration,
                    status="SUCCESS",
                    details={"filename": filename}
                )
                upload_timings.append(upload_timing)
                self.timings.append(upload_timing)
                
                time.sleep(1)
            except Exception as e:
                logger.error(f"Failed to upload file {i + 1}: {str(e)}")
                raise
        
        logger.info(f"Successfully uploaded {len(self.state.uploaded_files)} files")
    
    def _execute_request_signing(self):
        """Execute signing request"""
        json_payload = self._create_json_payload()
        headers = {
            'Authorization': f'Bearer {self.state.access_token}',
            'Content-Type': 'application/json'
        }
        
        response = self._make_request(
            "POST", 
            self.config.request_sign_url,
            json=json_payload,
            headers=headers
        )
        
        self.response_logger.log_response(
            "Request Sign",
            self.config.request_sign_url,
            response.status_code,
            response.json(),
            json_payload
        )
        
        # Extract auth URL and ID
        auth_url = response.json()["auth_urls"][0]["url"]
        self.state.id_rsa = auth_url.split("id=")[1].split("&")[0]
        logger.info(f"Got signing ID: {self.state.id_rsa}")
    
    def _execute_get_user_token(self):
        """Get user-specific token"""
        data = {
            "client_id": self.config.client_id,
            "client_secret": self.config.client_secret,
            "grant_type": "password",
            "username": self.config.username,
            "password": self.config.password
        }
        
        response = self._make_request("POST", self.config.access_token_url, data=data)
        self.response_logger.log_response(
            "Get User Token",
            self.config.access_token_url,
            response.status_code,
            response.json(),
            data
        )
        
        self.state.user_token = response.json()["access_token"]
    
    def _execute_auth_otp(self):
        """Execute OTP authentication"""
        url = (f"{self.config.auth_hash_url}?"
               f"user={self.state.user_identifier}&"
               f"id={self.state.id_rsa}&"
               f"channel_id={self.config.client_id}")
        
        headers = {
            'Authorization': f'Bearer {self.state.user_token}',
            'Content-Type': 'application/json'
        }
        
        data = {"otp_pin": self.config.otp_pin}
        
        response = self._make_request("POST", url, json=data, headers=headers)
        self.response_logger.log_response(
            "Auth OTP",
            url,
            response.status_code,
            response.json() if response.text else {},
            data
        )
    
    def _execute_signing(self):
        """Execute the signing process"""
        headers = {
            'Authorization': f'Bearer {self.state.access_token}',
            'Content-Type': 'application/json'
        }
        
        data = {
            "request_id": self.state.request_id,
            "user_identifier": self.state.user_identifier
        }
        
        response = self._make_request(
            "POST",
            self.config.execute_sign_url,
            json=data,
            headers=headers
        )
        
        self.response_logger.log_response(
            "Execute Sign",
            self.config.execute_sign_url,
            response.status_code,
            response.json() if response.text else {},
            data
        )
    
    def _execute_check_status(self):
        """Check signing status until completion"""
        headers = {
            'Authorization': f'Bearer {self.state.access_token}',
            'Content-Type': 'application/json'
        }
        
        data = {"request_id": self.state.request_id}
        counter = 0
        
        while counter < self.config.max_status_checks:
            counter += 1
            response = self._make_request(
                "POST",
                self.config.check_sign_status_url,
                json=data,
                headers=headers
            )
            
            response_data = response.json()
            message = response_data.get("message", "")
            
            if counter == 1:  # Log first response
                self.response_logger.log_response(
                    "Check Sign Status",
                    self.config.check_sign_status_url,
                    response.status_code,
                    response_data,
                    data
                )
            
            logger.info(f"Status check {counter}: {message}")
            
            if message == "DONE":
                logger.info(f"Signing completed after {counter} checks")
                break
            
            time.sleep(self.config.status_check_interval)
        else:
            logger.warning(f"Status check timeout after {counter} attempts")
    
    def _save_results(self):
        """Save timing results to files"""
        # Save to JSON
        json_results = {
            "test_info": {
                "request_id": self.state.request_id,
                "start_time": self.timings[0].start_time_formatted if self.timings else "",
                "end_time": self.timings[-1].end_time_formatted if self.timings else "",
                "total_duration": sum(t.duration for t in self.timings),
                "number_of_files": len(self.state.uploaded_files)
            },
            "timings": [asdict(t) for t in self.timings],
            "summary": self._calculate_summary()
        }
        
        with open("timing_results.json", 'w') as f:
            json.dump(json_results, f, indent=2)
        
        # Save to CSV
        with open("timing_results.csv", 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([
                "Operation", "Start Time", "End Time", 
                "Duration (s)", "Status", "Details"
            ])
            
            for timing in self.timings:
                writer.writerow([
                    timing.operation,
                    timing.start_time_formatted,
                    timing.end_time_formatted,
                    f"{timing.duration:.3f}",
                    timing.status,
                    json.dumps(timing.details) if timing.details else ""
                ])
        
        logger.info("Results saved to timing_results.json and timing_results.csv")
    
    def _calculate_summary(self) -> Dict[str, Any]:
        """Calculate summary statistics"""
        summary = {}
        
        # Group timings by operation type
        operations = {}
        for timing in self.timings:
            base_op = timing.operation.split(" ")[0]  # Get base operation name
            if base_op not in operations:
                operations[base_op] = []
            operations[base_op].append(timing.duration)
        
        # Calculate stats for each operation type
        for op, durations in operations.items():
            summary[op] = {
                "count": len(durations),
                "total": sum(durations),
                "average": sum(durations) / len(durations) if durations else 0,
                "min": min(durations) if durations else 0,
                "max": max(durations) if durations else 0
            }
        
        return summary


def format_timestamp(timestamp_ms: float, include_millis: bool = True, offset_hours: int = 0) -> str:
    """Format timestamp to match k6 format"""
    dt = datetime.fromtimestamp(timestamp_ms / 1000)
    
    if offset_hours:
        dt = dt.replace(hour=dt.hour + offset_hours)
    
    if include_millis:
        return dt.strftime("%Y-%m-%d jam %H:%M:%S.%f")[:-3]
    else:
        return dt.strftime("%Y-%m-%d jam %H:%M:%S")


def main():
    """Main entry point"""
    logger.info("Starting Document Signing Performance Test")
    
    # Create config (can be modified here or loaded from file)
    config = SigningTestConfig()
    
    # Run test
    test = SigningPerformanceTest(config)
    test.run()
    
    logger.info("Test completed successfully")


if __name__ == "__main__":
    main()