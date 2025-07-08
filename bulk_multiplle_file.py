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
import signal
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field, asdict
from functools import wraps
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,  # Changed to DEBUG for more details
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
    number_of_uploads: int = 100
    sign_per_doc: int = 3
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


@dataclass
class CheckpointData:
    """Data for checkpoint/resume functionality"""
    request_id: str = ""
    access_token: str = ""
    user_token: str = ""
    uploaded_files: List[str] = field(default_factory=list)
    completed_steps: List[str] = field(default_factory=list)
    last_completed_step: str = ""
    timestamp: str = ""
    id_rsa: str = ""  # Add id_rsa to checkpoint
    
    def save(self, filename: str = "checkpoint.json"):
        """Save checkpoint to file"""
        self.timestamp = datetime.now().isoformat()
        with open(filename, 'w') as f:
            json.dump(asdict(self), f, indent=2)
        logger.info(f"Checkpoint saved to {filename}")
    
    @classmethod
    def load(cls, filename: str = "checkpoint.json") -> Optional['CheckpointData']:
        """Load checkpoint from file"""
        try:
            with open(filename, 'r') as f:
                data = json.load(f)
                return cls(**data)
        except FileNotFoundError:
            return None
        except Exception as e:
            logger.error(f"Failed to load checkpoint: {str(e)}")
            return None


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


def format_timestamp(timestamp_ms: float, include_millis: bool = True, offset_hours: int = 0) -> str:
    """Format timestamp to match k6 format"""
    dt = datetime.fromtimestamp(timestamp_ms / 1000)
    
    if offset_hours:
        dt = dt.replace(hour=dt.hour + offset_hours)
    
    if include_millis:
        return dt.strftime("%Y-%m-%d jam %H:%M:%S.%f")[:-3]
    else:
        return dt.strftime("%Y-%m-%d jam %H:%M:%S")


@dataclass
class CheckpointData:
    """Data for checkpoint/resume functionality"""
    request_id: str = ""
    access_token: str = ""
    user_token: str = ""
    uploaded_files: List[str] = field(default_factory=list)
    completed_steps: List[str] = field(default_factory=list)
    last_completed_step: str = ""
    timestamp: str = ""
    id_rsa: str = ""  # Add id_rsa to checkpoint
    
    def save(self, filename: str = "checkpoint.json"):
        """Save checkpoint to file"""
        self.timestamp = datetime.now().isoformat()
        with open(filename, 'w') as f:
            json.dump(asdict(self), f, indent=2)
        logger.info(f"Checkpoint saved to {filename}")
    
    @classmethod
    def load(cls, filename: str = "checkpoint.json") -> Optional['CheckpointData']:
        """Load checkpoint from file"""
        try:
            with open(filename, 'r') as f:
                data = json.load(f)
                return cls(**data)
        except FileNotFoundError:
            return None
        except Exception as e:
            logger.error(f"Failed to load checkpoint: {str(e)}")
            return None


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
    def __init__(self, config: SigningTestConfig, resume: bool = False):
        self.config = config
        self.state = SigningTestState()
        self.timings: List[TimingResult] = []
        self.response_logger = ResponseLogger()
        self.session = self._create_session()
        self._interrupted = False
        self.checkpoint = CheckpointData()
        self.resume_mode = resume
        
        # Setup signal handler for Ctrl+C
        signal.signal(signal.SIGINT, self._signal_handler)
        
        # Try to load checkpoint if resume mode
        if resume:
            self._load_checkpoint()
    
    def _signal_handler(self, signum, frame):
        """Handle Ctrl+C gracefully"""
        logger.warning("\nReceived interrupt signal (Ctrl+C). Saving results and checkpoint...")
        self._interrupted = True
        self._save_checkpoint()
        self._save_results()
        self.response_logger.save_to_file()
        logger.info("Results and checkpoint saved. You can resume with --resume flag. Exiting...")
        sys.exit(0)
    
    def _save_checkpoint(self):
        """Save current progress to checkpoint file"""
        self.checkpoint.request_id = self.state.request_id
        self.checkpoint.access_token = self.state.access_token
        self.checkpoint.user_token = self.state.user_token
        self.checkpoint.uploaded_files = self.state.uploaded_files.copy()
        self.checkpoint.save()
    
    def _load_checkpoint(self):
        """Load checkpoint and restore state"""
        checkpoint = CheckpointData.load()
        if checkpoint:
            logger.info(f"Found checkpoint from {checkpoint.timestamp}")
            logger.info(f"Request ID: {checkpoint.request_id}")
            logger.info(f"Uploaded files: {len(checkpoint.uploaded_files)}")
            logger.info(f"Last completed step: {checkpoint.last_completed_step}")
            
            # Restore state
            self.state.request_id = checkpoint.request_id
            self.state.access_token = checkpoint.access_token
            self.state.user_token = checkpoint.user_token
            self.state.uploaded_files = checkpoint.uploaded_files
            self.checkpoint = checkpoint
            
            # Verify tokens are still valid
            if checkpoint.access_token:
                try:
                    # Test token with a simple request
                    headers = {'Authorization': f'Bearer {checkpoint.access_token}'}
                    test_response = self.session.get(
                        self.config.check_sign_status_url.replace('plus-checksignstatus', 'health'),
                        headers=headers,
                        timeout=5
                    )
                    if test_response.status_code == 401:
                        logger.warning("Access token expired, will refresh...")
                        self.state.access_token = ""
                except:
                    logger.warning("Could not verify access token, will refresh...")
                    self.state.access_token = ""
            
            return True
        else:
            logger.info("No checkpoint found, starting fresh...")
            return False
        
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
    
    def retry_with_backoff(self, func, *args, **kwargs):
        """Execute function with retry logic and exponential backoff"""
        max_retries = kwargs.pop('max_retries', self.config.max_retries)
        operation_name = kwargs.pop('operation_name', func.__name__)
        
        for attempt in range(max_retries + 1):
            try:
                if attempt > 0:
                    # Exponential backoff: 2^attempt * backoff_factor seconds
                    wait_time = (2 ** attempt) * self.config.retry_backoff_factor
                    logger.info(f"Retry attempt {attempt}/{max_retries} for {operation_name} after {wait_time:.1f}s...")
                    time.sleep(wait_time)
                
                return func(*args, **kwargs)
                
            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 401:
                    logger.warning(f"Got 401 for {operation_name}, refreshing token...")
                    try:
                        self._get_access_token()
                        # Note: Token refresh happens, but headers need to be updated in the calling function
                        continue  # Retry with new token
                    except Exception as token_error:
                        logger.error(f"Failed to refresh token: {str(token_error)}")
                        if attempt == max_retries:
                            raise
                elif 400 <= e.response.status_code < 500:
                    # Client errors (except 401) usually don't benefit from retry
                    logger.error(f"Client error {e.response.status_code} for {operation_name}: {str(e)}")
                    raise
                else:
                    # Server errors (5xx) - retry
                    logger.warning(f"Server error {e.response.status_code} for {operation_name}: {str(e)}")
                    if attempt == max_retries:
                        raise
                        
            except (requests.exceptions.ConnectionError, 
                    requests.exceptions.Timeout,
                    requests.exceptions.RequestException) as e:
                logger.warning(f"Network error for {operation_name}: {str(e)}")
                if attempt == max_retries:
                    raise
                    
            except Exception as e:
                logger.error(f"Unexpected error for {operation_name}: {str(e)}")
                raise
        
        raise Exception(f"Max retries ({max_retries}) exceeded for {operation_name}")
    
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
        """Make HTTP request with timeout and logging"""
        kwargs.setdefault('timeout', self.config.request_timeout)
        
        # Log request details for debugging
        logger.debug(f"Making {method} request to {url}")
        if 'json' in kwargs:
            logger.debug(f"Request body: {json.dumps(kwargs['json'], indent=2)}")
        if 'data' in kwargs:
            logger.debug(f"Request data: {kwargs['data']}")
        if 'headers' in kwargs:
            # Hide sensitive auth tokens in logs
            safe_headers = {k: v if k.lower() != 'authorization' else 'Bearer ***' 
                          for k, v in kwargs['headers'].items()}
            logger.debug(f"Request headers: {safe_headers}")
        
        try:
            response = self.session.request(method, url, **kwargs)
            logger.debug(f"Response status: {response.status_code}")
            
            # Log response body for error cases
            if response.status_code >= 400:
                try:
                    logger.error(f"Error response body: {response.json()}")
                except:
                    logger.error(f"Error response text: {response.text}")
            
            response.raise_for_status()
            return response
        except requests.exceptions.HTTPError as e:
            # Log more details for 400 errors
            if e.response.status_code == 400:
                logger.error(f"Bad Request (400) for {url}")
                try:
                    error_detail = e.response.json()
                    logger.error(f"Error details: {json.dumps(error_detail, indent=2)}")
                except:
                    logger.error(f"Error response: {e.response.text}")
            raise
    
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
        
        def do_upload():
            with open(self.config.pdf_file_path, 'rb') as f:
                files = {'file': ('10-pg-blank.pdf', f, 'application/pdf')}
                headers = {'Authorization': f'Bearer {self.state.access_token}'}
                
                response = self._make_request("POST", self.config.upload_url, files=files, headers=headers)
                
                self.response_logger.log_response(
                    f"Upload File {file_index + 1}",
                    self.config.upload_url,
                    response.status_code,
                    response.json()
                )
                
                return response.json()["filename"]
        
        filename = self.retry_with_backoff(
            do_upload,
            operation_name=f"Upload File {file_index + 1}"
        )
        
        duration = time.time() - start_time
        return filename, duration
    
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
        # Initialize test or use checkpoint
        if not self.resume_mode or not self.checkpoint.request_id:
            self.state.request_id = self.generate_random_id(6)
            self.state.user_identifier = self.config.username
            logger.info(f"Starting NEW test with request_id: {self.state.request_id}")
        else:
            self.state.user_identifier = self.config.username
            logger.info(f"RESUMING test with request_id: {self.state.request_id}")
        
        steps = [
            ("Get JWT Token", self._execute_get_token, False),  # Always run
            ("Upload Files", self._execute_upload_files, True),  # Can resume
            ("Request Sign", self._execute_request_signing, True),
            ("Get User Token", self._execute_get_user_token, False),  # Always run
            ("Auth using OTP", self._execute_auth_otp, True),
            ("Execute Sign", self._execute_signing, True),
            ("Check Sign Status", self._execute_check_status, True)
        ]
        
        try:
            for step_name, step_func, resumable in steps:
                # Skip if already completed and resumable
                if resumable and step_name in self.checkpoint.completed_steps:
                    logger.info(f"Skipping {step_name} (already completed)")
                    continue
                
                logger.info(f"\n{'='*50}")
                logger.info(f"Executing step: {step_name}")
                logger.info(f"{'='*50}")
                
                # Execute step with timing
                self._record_timing(step_name, step_func)
                
                # Mark step as completed
                if step_name not in self.checkpoint.completed_steps:
                    self.checkpoint.completed_steps.append(step_name)
                self.checkpoint.last_completed_step = step_name
                
                # Save checkpoint after each major step
                self._save_checkpoint()
                
        except KeyboardInterrupt:
            logger.warning("Test interrupted by user")
        except Exception as e:
            logger.error(f"Test failed at step '{self.checkpoint.last_completed_step}': {str(e)}")
            logger.info("You can resume from this point using --resume flag")
            if not self._interrupted:
                raise
        finally:
            # Always save what we have
            if not self._interrupted:
                self._save_checkpoint()
                self._save_results()
                self.response_logger.save_to_file()
                
                # Clear checkpoint on successful completion
                if "Check Sign Status" in self.checkpoint.completed_steps:
                    try:
                        import os
                        #os.remove("checkpoint.json")
                        logger.info(f"Test completed successfully, checkpoint removed {self.state.request_id}")
                    except:
                        pass
    
    def _execute_get_token(self):
        """Execute token retrieval"""
        self._get_access_token()
        time.sleep(1)
    
    def _execute_upload_files(self):
        """Execute file uploads with resume capability"""
        # Start from where we left off
        start_index = len(self.state.uploaded_files)
        
        if start_index > 0:
            logger.info(f"Resuming upload from file {start_index + 1}/{self.config.number_of_uploads}")
            logger.info(f"Already uploaded: {self.state.uploaded_files}")
        
        for i in range(start_index, self.config.number_of_uploads):
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
                self.timings.append(upload_timing)
                
                # Save checkpoint after each file
                if (i + 1) % 5 == 0:  # Save every 5 files
                    self._save_checkpoint()
                    logger.info(f"Checkpoint saved after {i + 1} files")
                
                time.sleep(1)
            except Exception as e:
                logger.error(f"Failed to upload file {i + 1}: {str(e)}")
                logger.info(f"Successfully uploaded {len(self.state.uploaded_files)} files before failure")
                raise
        
        logger.info(f"Successfully uploaded all {len(self.state.uploaded_files)} files")
    
    def _execute_request_signing(self):
        """Execute signing request"""
        # Check if we already have id_rsa from checkpoint
        if hasattr(self, 'checkpoint') and hasattr(self.checkpoint, 'id_rsa') and self.checkpoint.id_rsa:
            self.state.id_rsa = self.checkpoint.id_rsa
            logger.info(f"Using existing signing ID from checkpoint: {self.state.id_rsa}")
            return
        
        # Validate we have uploaded files
        if not self.state.uploaded_files:
            logger.error("No uploaded files found for signing request!")
            raise ValueError("Cannot create signing request without uploaded files")
        
        json_payload = self._create_json_payload()
        
        # Log payload for debugging
        logger.info(f"Creating signing request with {len(self.state.uploaded_files)} files")
        logger.debug(f"Request payload: {json.dumps(json_payload, indent=2)}")
        
        headers = {
            'Authorization': f'Bearer {self.state.access_token}',
            'Content-Type': 'application/json'
        }
        
        def do_request():
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
            response_data = response.json()
            
            # Check if auth_urls exists and has data
            if 'auth_urls' not in response_data or not response_data['auth_urls']:
                logger.error(f"No auth_urls in response: {response_data}")
                raise ValueError("Invalid response: missing auth_urls")
            
            auth_url = response_data["auth_urls"][0]["url"]
            self.state.id_rsa = auth_url.split("id=")[1].split("&")[0]
            logger.info(f"Got signing ID: {self.state.id_rsa}")
            
            # Save to checkpoint
            if hasattr(self, 'checkpoint'):
                self.checkpoint.id_rsa = self.state.id_rsa
            
            return response
        
        self.retry_with_backoff(
            do_request,
            operation_name="Request Sign"
        )
    
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
        
        def do_auth():
            response = self._make_request("POST", url, json=data, headers=headers)
            self.response_logger.log_response(
                "Auth OTP",
                url,
                response.status_code,
                response.json() if response.text else {},
                data
            )
            return response
        
        self.retry_with_backoff(
            do_auth,
            operation_name="Auth OTP"
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
        
        def do_execute():
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
            return response
        
        self.retry_with_backoff(
            do_execute,
            operation_name="Execute Sign"
        )
    
    def _execute_check_status(self):
        """Check signing status until completion"""
        headers = {
            'Authorization': f'Bearer {self.state.access_token}',
            'Content-Type': 'application/json'
        }
        
        data = {"request_id": self.state.request_id}
        counter = 0
        
        while counter < self.config.max_status_checks and not self._interrupted:
            counter += 1
            
            def do_check():
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
                
                return message
            
            try:
                message = self.retry_with_backoff(
                    do_check,
                    operation_name=f"Status Check {counter}",
                    max_retries=self.config.max_retries * 2  # More retries for status check
                )
                
                if message == "DONE":
                    logger.info(f"Signing completed after {counter} checks")
                    break
                    
            except Exception as e:
                logger.error(f"Failed to check status after retries: {str(e)}")
                # Continue checking even if one fails
                pass
            
            time.sleep(self.config.status_check_interval)
        else:
            if self._interrupted:
                logger.warning("Status check interrupted by user")
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
    import argparse
    
    parser = argparse.ArgumentParser(description='Document Signing Performance Test')
    parser.add_argument('--resume', action='store_true', help='Resume from checkpoint')
    parser.add_argument('--clear-checkpoint', action='store_true', help='Clear existing checkpoint')
    parser.add_argument('--config', type=str, help='Configuration file (JSON)')
    
    args = parser.parse_args()
    
    # Clear checkpoint if requested
    if args.clear_checkpoint:
        try:
            import os
            os.remove("checkpoint.json")
            logger.info("Checkpoint cleared")
        except FileNotFoundError:
            logger.info("No checkpoint to clear")
        except Exception as e:
            logger.error(f"Failed to clear checkpoint: {str(e)}")
        return
    
    logger.info("Starting Document Signing Performance Test")
    
    # Create config (can be modified here or loaded from file)
    config = SigningTestConfig()
    
    # Load config from file if provided
    if args.config:
        try:
            with open(args.config, 'r') as f:
                config_data = json.load(f)
                for key, value in config_data.items():
                    if hasattr(config, key):
                        setattr(config, key, value)
            logger.info(f"Configuration loaded from {args.config}")
        except Exception as e:
            logger.error(f"Failed to load config: {str(e)}")
            return
    
    # Run test with resume option
    test = SigningPerformanceTest(config, resume=args.resume)
    test.run()
    
    logger.info("Test completed successfully with request_id : ")


if __name__ == "__main__":
    main()
