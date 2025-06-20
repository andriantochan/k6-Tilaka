// k6-test.js
import http from 'k6/http';
import { check } from 'k6';
import { sleep } from 'k6';

// Set up test data variables
let accessToken = "";
const binFile = open('./10-pg-blank.pdf', 'b');

export const options = {
    vus: 100,
    duration : '10s'
};

export function setup() {
    const payload = {
        "client_id": "37e3cb48-affe-4c35-904a-f4ed7a24fcd6",
        "grant_type": "client_credentials",
        "client_secret": "9373da2b-24bd-4149-a423-70e9b54503e7"
        
    }

    const params = {
        headers: {
            'Content-Type': 'application/x-www-form-urlencoded'
        }
    };

    const loginResponse = http.post('https://dev-keycloak19.tilaka.id/auth/realms/dev-id/protocol/openid-connect/token',payload, params);
    
    // Get and store token
    const body = JSON.parse(loginResponse.body);
    accessToken = body.access_token;

    return { accessToken };  // Return as object
}

export default function (data) {  // Add data parameter
    // Use token from setup
    accessToken = data.accessToken;

    const formData = {
        file: http.file(binFile, '10-pg-blank.pdf'),
    };

    const params = {
        headers: {
            'Authorization': `Bearer ${accessToken}`
        },
    }

    const response = http.post('http://192.168.112.42:8088/api/v1/upload', formData, params);

    // const response_json = JSON.parse(response.body)

    console.log("Response status:", response.status);
    console.log("Response body:", response.body);
    console.log()
    
    sleep(1);
}