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

// Variables for file upload
const binFile = open('./10-pg-blank.pdf', 'b');

// Variables for upload
const UPLOAD_URL = "https://stg-api.tilaka.id/plus-upload";

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
		userIdentifier: `andriregstg379`,
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
	if (vars.uploadedFiles.length > 0) {
		const jsonRequest = createJsonPayload(vars);
		console.log(jsonRequest)
		
		try {
			// Use k6's file system to write the file
			const jsonString = JSON.stringify(jsonRequest, null, 2);
			// This will write to the k6 working directory
			// Note: In cloud execution, this might not be accessible
			open('request_body_sign.json', 'w').write(jsonString);

			// Log success metrics
			console.log(`Successfully created request with ID: ${vars.requestId}`);
			console.log(`Uploaded ${vars.uploadedFiles.length} files`);
		} catch (error) {
			console.error(`Error writing JSON file: ${error}`);
		}
	}
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
				page_number: PAGE_NUMBER + j,
			});
		}

		jsonData.list_pdf.push(pdfEntry);
	}

	return jsonData;
}

// Alternative approach using handleSummary if you want to output the file at the end of the test
export function handleSummary(data) {
    const jsonRequest = createJsonPayload({
        requestId: generateRandomId(6),
        userIdentifier: 'andriregstg379',
        uploadedFiles: [] // You would need to collect these during the test
    });
    
    return {
        'stdout': 'Test summary', // This goes to stdout
        'request_body_sign.json': JSON.stringify(jsonRequest, null, 2), // This is saved as a file
    };
}