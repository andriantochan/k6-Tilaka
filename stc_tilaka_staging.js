import http from 'k6/http';
import { check, group, sleep } from 'k6';
import { Counter, Rate, Trend } from 'k6/metrics';
import { FormData } from 'https://jslib.k6.io/formdata/0.0.2/index.js';
import { htmlReport } from "https://raw.githubusercontent.com/benc-uk/k6-reporter/main/dist/bundle.js";

// Custom metric untuk response time per endpoint
const BASEURL = 'https://stg-api.tilaka.id';
const BASEURL_TILAKA_LITE = 'https://stg-api.tilaka.id';
const ENDPOINT_UPLOAD = '/plus-upload';
const ENDPOINT_REQUEST_LIVE_SIGNATURE = '/plus-requestshortlivesign';
const CLIENT_ID = '37e3cb48-affe-4c35-904a-f4ed7a24fcd6';
const CLIENT_SECRET = 'a9a1e30f-91fa-44aa-be27-7e84452bb423';
const FILE_PDF_NAME = './docs/10-pg-blank.pdf';
const PDF_OPEN = open(FILE_PDF_NAME, 'b');
const base64_img = './docs/base64_img.txt';
const base64_img_open = open(base64_img);

// Tracking waktu pengujian
const TEST_START_TIME = Date.now();

// Success rate dan counter metrics
const groupSuccessRate = new Rate('group_success');

// Counters untuk setiap jenis permintaan
const tokenRequests = new Counter('token_requests');
const uploadRequests = new Counter('upload_requests');
const signatureRequests = new Counter('signature_requests');

// Success rate untuk setiap grup
const tokenSuccessRate = new Rate('token_success_rate');
const uploadSuccessRate = new Rate('upload_success_rate');
const signatureSuccessRate = new Rate('signature_success_rate');

// Failure rate untuk setiap grup
const tokenFailureRate = new Rate('token_failure_rate');
const uploadFailureRate = new Rate('upload_failure_rate');
const signatureFailureRate = new Rate('signature_failure_rate');

// Counters untuk transaksi bisnis
const successfulBusinessFlows = new Counter('successful_business_flows');
const failedBusinessFlows = new Counter('failed_business_flows');
const totalBusinessFlows = new Counter('total_business_flows');

// Business flow success rate
const businessFlowSuccessRate = new Rate('business_flow_success_rate');
const businessFlowFailureRate = new Rate('business_flow_failure_rate');

// Response time trends untuk setiap endpoint
const apiResponseTime = new Trend('api_response_time');
const tokenResponseTime = new Trend('token_response_time');
const uploadResponseTime = new Trend('upload_response_time');
const signatureResponseTime = new Trend('signature_response_time');

// Tracking untuk analysis
let requestCounter = 0;
let minResponseTime = Number.MAX_VALUE;
let maxResponseTime = 0;
let minRequestId = 0;
let maxRequestId = 0;

// Counters untuk debugging
let totalSuccessCount = 0; // Track total successful flows

export const options = {
  // Gunakan executor 'shared-iterations' dengan nilai yang lebih stabil
  scenarios: {
    load_test: {
      executor: 'shared-iterations',
      vus: 5,
      iterations: 50,
      maxDuration: '15m',
    },
  },
  thresholds: {
    http_req_duration: ['p(95)<500', 'p(99)<1000'],
    api_response_time: ['avg<300'],
    http_req_failed: ['rate<0.01'],
    'group_success{group:getToken}': ['rate>0.95'],
    'group_success{group:uploadFile}': ['rate>0.95'],
    'group_success{group:requestLiveSignature}': ['rate>0.95'],
    'token_response_time': ['avg<200', 'p(95)<300'],
    'upload_response_time': ['avg<300', 'p(95)<450'],
    'signature_response_time': ['avg<400', 'p(95)<600'],
  },
  summaryTrendStats: ['min', 'med', 'avg', 'p(90)', 'p(95)', 'p(99)', 'max', 'count'],
};

// Simpan waktu mulai secara global
export function setup() {
  console.log('Test starting at: ' + new Date().toISOString());
  return { startTime: Date.now() };
}

export default function (data) {
  // Increment request counter
  requestCounter++;
  
  // Catat bahwa satu transaksi bisnis dimulai
  totalBusinessFlows.add(1);
  
  let authToken;
  
  // Status keberhasilan untuk setiap grup
  let tokenSuccess = false;
  let uploadSuccess = false;
  let signatureSuccess = false;

  group('getToken', function () {
    const startTime = Date.now();
    
    try {
      // Selalu catat upaya token
      tokenRequests.add(1);
      
      let res = http.post(`${BASEURL}/auth`, {
        client_id: CLIENT_ID,
        client_secret: CLIENT_SECRET,
        grant_type: 'client_credentials',
      }, { 
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        tags: { 
          group: 'getToken', 
          endpoint: 'auth',
          request_num: requestCounter 
        }
      });
      
      const endTime = Date.now();
      const responseTime = endTime - startTime;
      
      // Metrics recording
      apiResponseTime.add(responseTime, { 
        endpoint: 'getToken',
        request_num: requestCounter 
      });
      
      tokenResponseTime.add(responseTime, { 
        request_num: requestCounter,
        timestamp: new Date().toISOString()
      });

      const success = check(res, {
        'token request successful': (r) => r.status === 200,
        'token received': (r) => r.json('access_token') !== '',
      }, { group: 'getToken' });

      if (!success) {
        tokenFailureRate.add(1);
        groupSuccessRate.add(false, { group: 'getToken' });
        return;
      }
      
      // Tandai token sukses dan catat
      tokenSuccess = true;
      tokenSuccessRate.add(1);
      
      authToken = res.json('access_token');
      groupSuccessRate.add(true, { group: 'getToken' });
    } catch (error) {
      console.error(`Error in getToken: ${error}`);
      tokenFailureRate.add(1);
      groupSuccessRate.add(false, { group: 'getToken' });
    }
  });

  if (!authToken) {
    failedBusinessFlows.add(1);
    businessFlowFailureRate.add(1);
    console.log(`token sukses = ${tokenSuccess}, upload sukses = false, signature sukses = false`);
    console.log(`Transaksi gagal: Token request gagal`);
    return; // Skip selanjutnya jika tidak ada token
  }

  const headers = { Authorization: `Bearer ${authToken}` };
  let fileName;

  group('uploadFile', function () {
    try {
      // Selalu catat upaya upload
      uploadRequests.add(1);
      
      const fd = new FormData();
      fd.append('file', http.file(PDF_OPEN, FILE_PDF_NAME.split('/')[2], 'application/pdf'));
      
      const uploadHeaders = {
        ...headers,
        'Content-Type': `multipart/form-data; boundary=${fd.boundary}`
      };

      const startTime = Date.now();
      let res = http.post(`${BASEURL_TILAKA_LITE}${ENDPOINT_UPLOAD}`, fd.body(), { 
        headers: uploadHeaders,
        tags: { 
          group: 'uploadFile', 
          endpoint: 'upload',
          request_num: requestCounter 
        }
      });
      
      const endTime = Date.now();
      const responseTime = endTime - startTime;
      
      // Metrics recording
      apiResponseTime.add(responseTime, { 
        endpoint: 'uploadFile',
        request_num: requestCounter 
      });
      
      uploadResponseTime.add(responseTime, { 
        request_num: requestCounter,
        timestamp: new Date().toISOString()
      });

      const success = check(res, {
        'upload file successful': (r) => r.status === 200,
        'file uploaded': (r) => r.json('filename') !== '',
      }, { group: 'uploadFile' });
      
      if (!success) {
        uploadFailureRate.add(1);
        groupSuccessRate.add(false, { group: 'uploadFile' });
        return;
      }
      
      // Tandai upload sukses dan catat
      uploadSuccess = true;
      uploadSuccessRate.add(1);
      
      fileName = res.json('filename');
      groupSuccessRate.add(true, { group: 'uploadFile' });
    } catch (error) {
      console.error(`Error in uploadFile: ${error}`);
      uploadFailureRate.add(1);
      groupSuccessRate.add(false, { group: 'uploadFile' });
    }
  });

  if (!fileName) {
    failedBusinessFlows.add(1);
    businessFlowFailureRate.add(1);
    console.log(`token sukses = ${tokenSuccess}, upload sukses = ${uploadSuccess}, signature sukses = false`);
    console.log(`Transaksi gagal: Upload request gagal`);
    return; // Skip selanjutnya jika tidak ada file
  }

  group('requestLiveSignature', function () {
    try {
      // Selalu catat upaya signature
      signatureRequests.add(1);
      
      const NIK = generateRandom16DigitNumber();
      const dataJson = {
        "user": {
          "nik": `${NIK}`,
          "email": `adnan_loadtest_${NIK}@yopmail.com`,
          "name": 'Adnan Load Test',
          "photo_ktp": `${base64_img_open}`,
          "photo_selfie": `${base64_img_open}`,
          "consent_text": "test abc 12345",
          "version": "TNT-STG-v.1.0.0",
          "is_approved": true,
          "consent_timestamp": "2024-10-01 10:05:50",
          "hash_consent": "ddef508ddcf0e69e8179e4e0690542eeebc88d7dd4a5591257aea2358becb27c"
        },
        "signing": {
          "signatures": [
            {
              "signature_image": `${base64_img_open}`
            }
          ],
          "list_pdf": [
            {
              "filename": fileName,
              "signatures": [
                {
                  "width": 152,
                  "height": 58,
                  "reason": "Hash sign staging",
                  "location": "Permata Hijau",
                  "coordinate_x": 200,
                  "coordinate_y": 189,
                  "page_number": 1,
                  "qr_option": "QRONLY"
                }
              ]
            }
          ]
        }
      };

      const startTime = Date.now();
      const signHeaders = {
        ...headers,
        'Content-Type': 'application/json'
      };
      
      let res = http.post(`${BASEURL_TILAKA_LITE}${ENDPOINT_REQUEST_LIVE_SIGNATURE}`, 
        JSON.stringify(dataJson), { 
          headers: signHeaders,
          tags: { 
            group: 'requestLiveSignature', 
            endpoint: 'signature',
            request_num: requestCounter 
          }
        }
      );
      
      const endTime = Date.now();
      const responseTime = endTime - startTime;
      const timestamp = new Date().toISOString();
      
      // Metrics recording
      apiResponseTime.add(responseTime, { 
        endpoint: 'requestLiveSignature',
        request_num: requestCounter 
      });
      
      signatureResponseTime.add(responseTime, { 
        request_num: requestCounter,
        timestamp: timestamp
      });
      
      // Track min/max for analysis
      if (responseTime < minResponseTime) {
        minResponseTime = responseTime;
        minRequestId = requestCounter;
      }
      
      if (responseTime > maxResponseTime) {
        maxResponseTime = responseTime;
        maxRequestId = requestCounter;
      }

      const success = check(res, {
        'request live signature successful': (r) => r.status === 200,
        'request live signature request_id': (r) => {
          const body = r.json();
          return body.data && body.data.request_id !== '';
        },
      }, { group: 'requestLiveSignature' });
      
      if (!success) {
        signatureFailureRate.add(1);
        groupSuccessRate.add(false, { group: 'requestLiveSignature' });
        console.error(`Error in requestLiveSignature: ${res.body}`);
        return;
      }
      
      // Tandai signature sukses dan catat
      signatureSuccess = true;
      signatureSuccessRate.add(1);
      
      groupSuccessRate.add(true, { group: 'requestLiveSignature' });
    } catch (error) {
      console.error(`Error in requestLiveSignature: ${error}`);
      signatureFailureRate.add(1);
      groupSuccessRate.add(false, { group: 'requestLiveSignature' });
    }
  });
  
  // Menentukan keberhasilan keseluruhan transaksi bisnis
  if (tokenSuccess && uploadSuccess && signatureSuccess) {
    // Jika semua grup sukses, maka seluruh transaksi sukses
    successfulBusinessFlows.add(1);
    businessFlowSuccessRate.add(1);
    totalSuccessCount++; // Menambah counter debug
    console.log(`token sukses = ${tokenSuccess}, upload sukses = ${uploadSuccess}, signature sukses = ${signatureSuccess}`);
    console.log(`Transaksi sukses: ${totalSuccessCount}`);
  } else {
    // Jika ada grup yang gagal, maka seluruh transaksi gagal
    failedBusinessFlows.add(1);
    businessFlowFailureRate.add(1);
    console.log(`token sukses = ${tokenSuccess}, upload sukses = ${uploadSuccess}, signature sukses = ${signatureSuccess}`);
    console.log(`Transaksi gagal: Salah satu atau lebih langkah gagal`);
  }
  
  // Add a small sleep untuk think time yang realistis
  sleep(0.3);
}

function generateRandom16DigitNumber() {
  const min = 1000000000000000;
  const max = 9999999999999999;
  return Math.floor(Math.random() * (max - min + 1)) + min;
}

// Function for finishing the test - track end time
export function teardown(data) {
  // Simpan waktu akhir pengujian
  const testEndTime = Date.now();
  const testStartTime = data.startTime || TEST_START_TIME;
  const testDuration = (testEndTime - testStartTime) / 1000;
  
  // Simpan durasi ke environment variable
  __ENV.TEST_DURATION = testDuration;
  
  // Catat waktu selesai dan durasi total untuk verifikasi
  console.log(`Test completed at: ${new Date().toISOString()}`);
  console.log(`Test duration: ${testDuration} seconds`);
  console.log(`Total successful business flows: ${totalSuccessCount}`);
}

// Fungsi untuk menghasilkan HTML report dengan grafik dan TPS analysis
export function handleSummary(data) {
  // Gunakan durasi yang disimpan di __ENV atau hitung dari timestamp
  let testDurationSeconds = 0;
  
  if (__ENV.TEST_DURATION) {
    testDurationSeconds = parseFloat(__ENV.TEST_DURATION);
    console.log(`Using TEST_DURATION from __ENV: ${testDurationSeconds} seconds`);
  }
  else if (data.timestamp && data.timestamp.endTime && data.timestamp.startTime) {
    testDurationSeconds = (data.timestamp.endTime - data.timestamp.startTime) / 1000;
    console.log(`Using timestamp-based duration: ${testDurationSeconds} seconds`);
  }
  else {
    // Fallback ke 60 detik jika tidak bisa mendapatkan durasi
    testDurationSeconds = 60;
    console.log(`WARNING: Unable to determine test duration, using fallback value of 60 seconds`);
  }
  
  // Pastikan durasinya tidak nol dan valid
  if (testDurationSeconds <= 0 || isNaN(testDurationSeconds)) {
    testDurationSeconds = 60; // Fallback 1 menit
    console.log(`WARNING: Invalid test duration, using fallback value of 60 seconds`);
  }
  
  // Handle case when minResponseTime is still at initial value
  if (minResponseTime === Number.MAX_VALUE) {
    minResponseTime = 0;
  }
  
  // Safely access metrics values
  const safeGet = (obj, path, defaultValue = 0) => {
    if (!obj) return defaultValue;
    const parts = path.split('.');
    let current = obj;
    for (const part of parts) {
      if (current[part] === undefined) return defaultValue;
      current = current[part];
    }
    return current;
  };
  
  // Dapatkan data metrik dari k6
  const tokenCount = safeGet(data, 'metrics.token_requests.values.count', 0);
  const uploadCount = safeGet(data, 'metrics.upload_requests.values.count', 0);
  const signatureCount = safeGet(data, 'metrics.signature_requests.values.count', 0);
  
  const tokenSuccessRateValue = safeGet(data, 'metrics.token_success_rate.values.rate', 0) * 100;
  const uploadSuccessRateValue = safeGet(data, 'metrics.upload_success_rate.values.rate', 0) * 100;
  const signatureSuccessRateValue = safeGet(data, 'metrics.signature_success_rate.values.rate', 0) * 100;
  
  const totalFlowCount = safeGet(data, 'metrics.total_business_flows.values.count', 0);
  const successfulFlowCount = safeGet(data, 'metrics.successful_business_flows.values.count', 0);
  const failedFlowCount = safeGet(data, 'metrics.failed_business_flows.values.count', 0);
  
  const businessFlowSuccessRateValue = safeGet(data, 'metrics.business_flow_success_rate.values.rate', 0) * 100;
  
  // Extend data with test duration
  const customData = {
    ...data,
    calculated_metrics: {
      test_duration_seconds: testDurationSeconds,
      
      // Response time analysis
      min_response_time: minResponseTime,
      max_response_time: maxResponseTime,
      min_request_id: minRequestId,
      max_request_id: maxRequestId
    }
  };
  
  try {
    // Generate HTML with TPS-specific section
    const html = htmlReport(customData);
    
    // Extend HTML with custom section for TPS
    const extendedHtml = html.replace('</body>', `
      <div class="card">
        <div class="header">
          <h2>Summary per Component</h2>
        </div>
        <div class="content">
          <table>
            <tr>
              <th>Component</th>
              <th>Total Count</th>
              <th>Rate (transactions/sec)</th>
              <th>Success Rate</th>
              <th>Avg Response Time</th>
              <th>P95 Response Time</th>
            </tr>
            <tr>
              <td>Token Requests</td>
              <td>${tokenCount}</td>
              <td>${safeGet(data, 'metrics.token_success_rate.values.rate', 0).toFixed(3)}</td>
              <td>${tokenSuccessRateValue.toFixed(2)}%</td>
              <td>${safeGet(data, 'metrics.token_response_time.values.avg', 0).toFixed(2)} ms</td>
              <td>${safeGet(data, 'metrics.token_response_time.values.p(95)', 0).toFixed(2)} ms</td>
            </tr>
            <tr>
              <td>Upload Requests</td>
              <td>${uploadCount}</td>
              <td>${safeGet(data, 'metrics.upload_success_rate.values.rate', 0).toFixed(3)}</td>
              <td>${uploadSuccessRateValue.toFixed(2)}%</td>
              <td>${safeGet(data, 'metrics.upload_response_time.values.avg', 0).toFixed(2)} ms</td>
              <td>${safeGet(data, 'metrics.upload_response_time.values.p(95)', 0).toFixed(2)} ms</td>
            </tr>
            <tr>
              <td>Signature Requests</td>
              <td>${signatureCount}</td>
              <td>${safeGet(data, 'metrics.signature_success_rate.values.rate', 0).toFixed(3)}</td>
              <td>${signatureSuccessRateValue.toFixed(2)}%</td>
              <td>${safeGet(data, 'metrics.signature_response_time.values.avg', 0).toFixed(2)} ms</td>
              <td>${safeGet(data, 'metrics.signature_response_time.values.p(95)', 0).toFixed(2)} ms</td>
            </tr>
            <tr class="highlight">
              <td><strong>Complete Business Flow (All 3 Steps)</strong></td>
              <td><strong>${totalFlowCount}</strong></td>
              <td><strong>${safeGet(data, 'metrics.business_flow_success_rate.values.rate', 0).toFixed(3)}</strong></td>
              <td><strong>${businessFlowSuccessRateValue.toFixed(2)}%</strong></td>
              <td colspan="2"><strong>Successful: ${successfulFlowCount} / Failed: ${failedFlowCount}</strong></td>
            </tr>
          </table>
          
          <div style="margin-top: 20px;">
            <p><strong>Test Duration: ${testDurationSeconds.toFixed(2)} seconds</strong></p>
            <p>Virtual Users (VUs): ${safeGet(data, 'metrics.vus.values.max', 'N/A')}</p>
            <p>Iterations: ${safeGet(data, 'metrics.iterations.values.count', 'N/A')}</p>
            <p><small>Note: Rate adalah jumlah transaksi per detik (TPS) selama pengujian.</small></p>
          </div>
        </div>
      </div>
      
      <div class="card">
        <div class="header">
          <h2>Response Time Analysis</h2>
        </div>
        <div class="content">
          <table>
            <tr>
              <th>Metric</th>
              <th>Value</th>
              <th>Request #</th>
            </tr>
            <tr>
              <td>Minimum Response Time (Signature)</td>
              <td>${minResponseTime} ms</td>
              <td>${minRequestId}</td>
            </tr>
            <tr>
              <td>Maximum Response Time (Signature)</td>
              <td>${maxResponseTime} ms</td>
              <td>${maxRequestId}</td>
            </tr>
          </table>
        </div>
      </div>
      
      <style>
        .highlight {
          background-color: #f0f8ff;
          font-weight: bold;
        }
      </style>
      </body>
    `);
    
    return {
      "summary_without_tps.html": extendedHtml,
      "summary_without_tps.json": JSON.stringify(customData, null, 2),
    };
  } catch (error) {
    console.error("Error generating summary: " + error);
    
    // Fallback to simple report
    return {
      "summary.txt": `
        Test Summary:
        - Test Duration: ${testDurationSeconds.toFixed(2)} seconds
        - Total Business Flow Attempts: ${totalFlowCount}
        - Successful Business Flows: ${successfulFlowCount} (${businessFlowSuccessRateValue.toFixed(2)}%)
        - Failed Business Flows: ${failedFlowCount} (${(100 - businessFlowSuccessRateValue).toFixed(2)}%)
        
        Per Component:
        - Token: Count=${tokenCount}, Rate=${safeGet(data, 'metrics.token_success_rate.values.rate', 0).toFixed(3)}, Success=${tokenSuccessRateValue.toFixed(2)}%
        - Upload: Count=${uploadCount}, Rate=${safeGet(data, 'metrics.upload_success_rate.values.rate', 0).toFixed(3)}, Success=${uploadSuccessRateValue.toFixed(2)}%
        - Signature: Count=${signatureCount}, Rate=${safeGet(data, 'metrics.signature_success_rate.values.rate', 0).toFixed(3)}, Success=${signatureSuccessRateValue.toFixed(2)}%
        
        Response Time:
        - Token: Avg=${safeGet(data, 'metrics.token_response_time.values.avg', 0).toFixed(2)} ms
        - Upload: Avg=${safeGet(data, 'metrics.upload_response_time.values.avg', 0).toFixed(2)} ms
        - Signature: Avg=${safeGet(data, 'metrics.signature_response_time.values.avg', 0).toFixed(2)} ms
      `,
      "summary.json": JSON.stringify(customData, null, 2),
    };
  }
}
