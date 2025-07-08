import http from "k6/http";
import { check, sleep } from "k6";
import { randomString } from "https://jslib.k6.io/k6-utils/1.2.0/index.js";


// Test configuration
export const options = {
	//   stages: [
	//     { duration: '30s', target: 5 },   // Ramp up to 5 users
	//     { duration: '1m', target: 10 },   // Ramp up to 10 users
	//     { duration: '2m', target: 10 },   // Stay at 10 users
	//     { duration: '30s', target: 0 },   // Ramp down to 0 users
	//   ],

	vus: 1,
	thresholds: {
		http_req_duration: ["p(95)<2000"], // 95% of requests should be below 2s
		http_req_failed: ["rate<0.05"], // Less than 5% of requests should fail
	},
};

// Variables for JWT token
const ACCESS_TOKEN_URL = "https://stg-api.tilaka.id/auth";
const CLIENT_ID = "37e3cb48-affe-4c35-904a-f4ed7a24fcd6";
const CLIENT_SECRET = "a9a1e30f-91fa-44aa-be27-7e84452bb423";
const GRANT_TYPE = "client_credentials";
const COMPANY_ID = "11111111-1111-1111-1111-111111111111"
const AUTH_HASH_URL = "https://stg-api.tilaka.id/signing-authhashsign?" 

// Variables for file upload
const binFile = open('./10-pg-blank.pdf', 'b');

// Variables for upload
const UPLOAD_URL = "https://stg-api.tilaka.id/plus-upload";

// Variables for request sign
const REQUEST_SIGN_URL = "https://stg-api.tilaka.id/plus-requestsign"

// Variables for execute sign
const EXECUTE_SIGN_URL = "https://stg-api.tilaka.id/plus-executesign"

// Variables for check sign status 
const CHECK_SIGN_STATUS_URL = "https://stg-api.tilaka.id/plus-checksignstatus"


// Variables for JSON creation
const COORD_X = 0;
const COORD_Y = 0;
const WIDTH = 200;
const HEIGHT = 100;
const PAGE_NUMBER = 1;
const SIGN_PER_DOC = 4;
const NUMBER_OF_UPLOAD = 5;

// Sample PDF content as base64 (replace with actual content or binary file)
// In a real scenario, you'd need to prepare test files to be used by k6
// Sample signature image as base64
const SIGNATURE_IMAGE = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=";

// Generate a random string of specified length
function generateRandomId(length) {
	return randomString(length, "abcdefghijklmnopqrstuvwxyz0123456789");
}

// Initialize variables for the test session
function setup() {
	// Initialize variables that will be shared throughout the test
	const vars = {
		accessToken: "",
		uploadedFiles: [],
		requestId: generateRandomId(6),
		userIdentifier: `andriregstg386`,
	};

	return vars;
}

export default function () {
	// Setup test variables
	const vars = setup();

	// Step 1: Get JWT token
	const tokenResponse = http.post(ACCESS_TOKEN_URL, {
		client_id: CLIENT_ID,
		client_secret: CLIENT_SECRET,
		grant_type: GRANT_TYPE,
	});

	check(tokenResponse, {
		"token request is successful": (r) => r.status === 200,
		"token response contains access_token": (r) =>
			r.json("access_token") !== undefined,
	});

	if (tokenResponse.status !== 200) {
		console.log(`Failed to get token. Status code: ${tokenResponse.status}`);
		console.log(`Response: ${tokenResponse.body}`);
		return;
	}

	const access_token = JSON.parse(tokenResponse.body).access_token

	vars.accessToken = access_token

	sleep(1); // Add a small delay between requests

	// Step 2: Upload files
	for (let i = 0; i < NUMBER_OF_UPLOAD; i++) {
		const uploadResponse = uploadFile(access_token);

		check(uploadResponse, {
			"upload is successful": (r) => r.status === 200,
			"upload response contains filename": (r) => r.json("filename") !== undefined,
		});

		if (uploadResponse.status === 200) {
			vars.uploadedFiles.push(uploadResponse.json("filename"));
		} else if (uploadResponse.status === 401) {
			// Handle token expiration
			console.log("Unauthorized. Getting new token...");
			const newTokenResponse = http.post(ACCESS_TOKEN_URL, {
				client_id: CLIENT_ID,
				client_secret: CLIENT_SECRET,
				grant_type: GRANT_TYPE,
			});

			if (newTokenResponse.status === 200) {
				vars.accessToken = JSON.parse(tokenResponse.body).access_token;
				const retryUpload = uploadFile(access_token);

				if (retryUpload.status === 200) {
					vars.uploadedFiles.push(retryUpload.json("body.filename"));
				}
			}
		}

		sleep(1); // Add a small delay between uploads
	}

	// Step 3: Create JSON request
	const jsonRequest = createJsonPayload(vars);
	console.log(typeof(jsonRequest))
	if (vars.uploadedFiles.length > 0) {
		try {
			// Convert JSON object to string with pretty formatting
			// const jsonString = JSON.stringify(jsonRequest, null, 2);

			// Log success metrics
			console.log(`Successfully created request with ID: ${vars.requestId}`);
			console.log(`Uploaded ${vars.uploadedFiles.length} files`);
		  } catch (error) {
			console.error(`Error writing JSON file: ${error}`);
		  }

		// Log success metrics
		console.log(`Successfully created request with ID: ${vars.requestId}`);
		console.log(`Uploaded ${vars.uploadedFiles.length} files`);

	}

	// Step 4: Request Sign
	const startTimeRequestSign = Date.now();
	console.log("---- Request sign start from", formatTimestamp(startTimeRequestSign)) // perlu datetime pencatatan sampai dapat response

	const AUTH_URL = requestSigning(vars.accessToken,JSON.stringify(jsonRequest))
	console.log("response : ", AUTH_URL.body)

	const stopTimeRequestSign = Date.now();
	console.log("---- Request sign end at", formatTimestamp(stopTimeRequestSign)) // perlu datetime pencatatan sampai dapat response
	console.log("---- Time taken for request sign: ", (stopTimeRequestSign - startTimeRequestSign) / 1000, "seconds")

	const parsedAuth = JSON.parse(AUTH_URL.body).auth_urls[0].url
	const idRsa = parsedAuth.match(/id=([^&]+)/)?.[1];
	console.log("url auth: ",parsedAuth)
	console.log("id signing : ",idRsa)

	// Creating user token
	console.log("Creating user token")
	const user_token_response = http.post(ACCESS_TOKEN_URL, {
		client_id: CLIENT_ID,
		client_secret: CLIENT_SECRET,
		grant_type: "password",
		username: vars.userIdentifier,
		password: "Password123#"
	});
	const token_user_raw = user_token_response.body
	const token_user = JSON.parse(token_user_raw).access_token
	// console.log("user_token",token_user)

	// Step 4 : auth using OTP
	const startTimeAuth = Date.now();
	console.log("---- Auth using OTP start from", formatTimestamp(startTimeAuth)) // perlu datetime pencatatan sampai dapat response
	console.log("Processing Auth")
	const params = {
		headers: {
			'Authorization': `Bearer ${token_user}`,
			'Content-type': 'application/json'
		}
	}
	// const bodyAuth = {
	// 	face_image : SELFIE_IMAGE
	// }
	const bodyAuth = {
		otp_pin: "985070"
	}
	const auth_hash_url_complete = AUTH_HASH_URL+`user=${vars.userIdentifier}&id=${idRsa}&channel_id=${CLIENT_ID}`
	console.log(auth_hash_url_complete)
	const res_auth = http.post(auth_hash_url_complete,JSON.stringify(bodyAuth),params)
	console.log(res_auth.body)
	const stopTimeAuth = Date.now();
	console.log("---- Auth using OTP end at", formatTimestamp(stopTimeAuth)) // perlu datetime pencatatan sampai dapat response
	console.log("---- Time taken for auth using OTP: ", (stopTimeAuth - startTimeAuth) / 1000, "seconds")

	// Step 5: Execute Sign
	const startTimeExecute = Date.now();
	console.log("---- Execute Sign start from", formatTimestamp(startTimeExecute)) // perlu datetime pencatatan sampai dapat response

	console.log("Melakukan Execute Sign")
	const bodyExecute = {
		request_id: vars.requestId,
		user_identifier: vars.userIdentifier
	}
	// ---- 
	const executedSign = executeSigning(vars.accessToken,JSON.stringify(bodyExecute))
	console.log(executedSign.body)
	const stopTimeExecute = Date.now();
	console.log("---- Execute Sign end at", formatTimestamp(stopTimeExecute)) // perlu datetime pencatatan sampai dapat response
	console.log("---- Time taken for execute sign: ", (stopTimeExecute - startTimeExecute) / 1000, "seconds")

	// Step 6 : Check Sign Status
	const startTimeCheckStatus = Date.now();
	console.log("---- Check Sign Status start from", formatTimestamp(startTimeCheckStatus)) // perlu datetime pencatatan sampai dapat response
	console.log("Pengecekan sign status")
	const bodySignStatus = {
		request_id: vars.requestId
	}
	let signedStatus = checkSignStatus(vars.accessToken,JSON.stringify(bodySignStatus))
	let signedStatusBody = signedStatus.body
	let message = JSON.parse(signedStatusBody).message
	console.log(message)

	let counter = 1
	let max_counter = 10

	while(message!="DONE" && counter<=max_counter){
		counter++
		signedStatus = checkSignStatus(vars.accessToken,JSON.stringify(bodySignStatus))
		signedStatusBody = signedStatus.body
	 	message = JSON.parse(signedStatusBody).message
		console.log(`pengecekan status ke : ${counter} \n`, message)
		sleep(5)
	}
	const stopTimeCheckStatus = Date.now();
	console.log("---- Check Sign Status end at", formatTimestamp(stopTimeCheckStatus)) // perlu datetime pencatatan sampai dapat response
	console.log("---- Time taken for check sign status: ", (stopTimeCheckStatus - startTimeCheckStatus) / 1000, "seconds")
}

// Helper function to upload a file
function uploadFile(token) {
	
	const formData = {
		file: http.file(binFile, '10-pg-blank.pdf'),
	};
	
	const params = {
		headers: {
			'Authorization': `Bearer ${token}`
		},
	}
	
	const response = http.post(UPLOAD_URL, formData, params);

  
	return response;
}

// Helper function to create the JSON payload
function createJsonPayload(vars) {
	const jsonData = {
		request_id: vars.requestId,
		signatures: [
			{
				user_identifier: vars.userIdentifier,
				signature_image: SIGNATURE_IMAGE,
				sequence: 1,
			},
		],
		list_pdf: [],
	};

	// Create list_pdf entries based on uploaded filenames
	for (let i = 0; i < vars.uploadedFiles.length; i++) {
		const pdfEntry = {
			filename: vars.uploadedFiles[i],
			signatures: [],
		};

		// Add signatures based on sign_per_doc
		for (let j = 0; j < SIGN_PER_DOC; j++) {
			pdfEntry.signatures.push({
				user_identifier: vars.userIdentifier,
				width: WIDTH,
				height: HEIGHT,
				coordinate_x: COORD_X,
				coordinate_y: COORD_Y,
				page_number: PAGE_NUMBER,
			});
		}

		jsonData.list_pdf.push(pdfEntry);
	}

	return jsonData;
}

function requestSigning(token, vars){
	const params = {
		headers: {
			'Authorization': `Bearer ${token}`,
			'Content-type': 'application/json'
		}
	}

	const response = http.post(REQUEST_SIGN_URL, vars, params);
	return response;
}

function executeSigning(token,vars){
	const params = {
		headers: {
			'Authorization': `Bearer ${token}`,
			'Content-type': 'application/json'
		}
	}

	const response = http.post(EXECUTE_SIGN_URL, vars, params);
	return response;
}

function checkSignStatus(token,vars){
	const params = {
		headers: {
			'Authorization': `Bearer ${token}`,
			'Content-type': 'application/json'
		}
	}

	const response = http.post(CHECK_SIGN_STATUS_URL, vars, params);
	return response;
}

function formatTimestamp(timestamp, includeMillis = true, offsetHours = 0) {
    const date = new Date(timestamp);
    date.setHours(date.getHours() + offsetHours); // Offset manual kalau perlu (misal UTC+7)

    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    const hours = String(date.getHours()).padStart(2, '0');
    const minutes = String(date.getMinutes()).padStart(2, '0');
    const seconds = String(date.getSeconds()).padStart(2, '0');

    let formatted = `${year}-${month}-${day} jam ${hours}:${minutes}:${seconds}`;

    if (includeMillis) {
        const millis = String(date.getMilliseconds()).padStart(3, '0');
        formatted += `.${millis}`;
    }

    return formatted;
}