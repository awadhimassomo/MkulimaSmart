/**
 * Utility functions for client-side cryptographic operations
 */

// Convert Base64 URL safe string to ArrayBuffer
function b64ToArrayBuffer(base64) {
    // Replace URL-safe characters back to standard base64 characters
    base64 = base64.replace(/-/g, '+').replace(/_/g, '/');
    
    // Add padding if needed
    while (base64.length % 4 !== 0) {
        base64 += '=';
    }
    
    const binaryString = window.atob(base64);
    const bytes = new Uint8Array(binaryString.length);
    for (let i = 0; i < binaryString.length; i++) {
        bytes[i] = binaryString.charCodeAt(i);
    }
    return bytes.buffer;
}

// Create a blob URL from an ArrayBuffer with the specified MIME type
function arrayBufferToObjectUrl(buffer, mimeType = 'application/octet-stream') {
    const blob = new Blob([buffer], { type: mimeType });
    return URL.createObjectURL(blob);
}

// Retrieve the private RSA key from storage
async function getPrivateKey() {
    // TODO: Implement actual key retrieval from secure storage (IndexedDB, etc.)
    // For now, return a hardcoded test key (this should be replaced in production)
    
    // This is a placeholder for demo/testing only - in production, keys should be securely stored
    const testKeyJwk = {
        "kty": "RSA",
        "alg": "RSA-OAEP-256",
        "d": "XcE5NgSV4RY2qcRWHJh_A9f9SIMr0HX7IqsW5Qbc_Bwz3ukZZCjESWUjRjHjinDwXIAI3q2g7OYsjiiiiDUHjzkJGzZjgEh4jMh9jELTYHYXN_OYFRxp9-kQGzBGHlmKJSAkPj4E5TOnxjUYyZ_8LWm2UaAk6XF5qaDJ7YGZ5wz-SJGwQOQGhIXYI2oM5izA1FxvhxYEFBQkZsZCGl5V0xT-45aN8ye9cFYoAueKTVQHsYxTYEm7LD1MxCjaZ2Y-oZP66HXLLvgUt2RSuUrmq0PZ_2o9pXZPAmLuLRfXAg4MO-WqHLXLeCS5iVBZGYJdoUxNvAJJR0UdoJ33sw",
        "dp": "l-KpvOJ9Ps_63YkB66K3adLCIJ5u5mQNjSRoQ-Psneok3P3RyUlHP7CF7M4atQ2kpo6147jJtZVj7HaVDEFnf2OrbLGMX_f4s5Bq8gcT3Gn0a0yeCEOgd9EfvTVJ1JxM2jZFAT9kF7muEEanuuQGkYZnLAxEw_wJcpKOYiIQjIs",
        "dq": "hfr0wa7sRX5NCzbJnYURrNAbMRwy6UjQYnNDo2tBO8MbG_C89vS_3HKRmjNYVGwMiBGSKNZlDk7cEQFGpMrnSKjnXUfNPyPre3EjVrEpWnZ3R7BNj44Wfx25JN5NU9hVLPenw7qzUvpOJ28xPCUVIv3GvXKMHoHRgyjHHZurcQE",
        "e": "AQAB",
        "n": "mrqGjtVJfzWWJBgABwdXvLiRaTbZY9KJHj6BXRnlK4YhPP8XGY5R3J_3cGKWZM2j0QFbxIf7Z_r3iSnMYZnw3JCqIz50OatUVGgtaM6ay2Y3U1O82iAwKJgEcdz7Mj3sKV9Fy5JjuENa4ZQmQwzoEVTLNK8uJZPWBLKg6lv9y1Tmfmop78__NC2b0-CJibmXe5T4wKXZdFFOKtNKoHlqIiKZlPVaplIQWkK7vBY7OzYJGFJsOKJZQHsBgVRIYO3caAJbaJDjVZafHRHYzJOkQ6iN3GKiMYJQCBbjGqEI2BwU5_yX9VTsWkXxP9_tTpbFzLyXsF5PIho-AZwNZWPKjQ",
        "p": "yOUvYjxXCmm69NnSX-UYE8G3AXlXMU3WqOX9zvFlYpUYm_skdZwcQKJV1FvxNBpmbgx74FmSNPKT-T3nW0V3ME8p1EPihX9XNfQS9J12jhgbZ0mXkAuhgCIAyjmJ_C0QdXW8HSjJSj1UitV3fRLB1G3Ajl6C1JQCQtHgFZGZgE8",
        "q": "x8xR3D-5BXDiMqYkf7s03xBXt4l5tTlKJFEH1nOyJjQ_TsBTUHMM2NMQXlQnYJuhD7RqOziyLKLdGZDnL23V2o84fafQMqBE9zLbKKCXAC70i_7wroGXEqJzXppAS1jvB1T68BbhAZVKQpBT84OAgNQORi_2otr2MgKQnJ7rx3s",
        "qi": "hIQZvdnNkYfCYbmHNe0FnOGhbsWB3F4Y7rRZB6JvlXzJRwu_bhm3EjIEQxwYSVPAtoqgCQ43qVTYGZ3NCwpG7U3DYaP2CI1wLBoE9_-pIL9n5uL7vfBjCD0FDLZC1YCErq-t6jiNJxmTYxOdwNKYDZvQiAMYheXY3-i5DHyHk9Q"
    };
    
    try {
        // Import the test key into the WebCrypto API
        return await window.crypto.subtle.importKey(
            "jwk",
            testKeyJwk,
            {
                name: "RSA-OAEP",
                hash: {name: "SHA-256"}
            },
            false, // extractable
            ["decrypt"] // allowed operations
        );
    } catch (error) {
        console.error("Error importing private key:", error);
        throw new Error("Failed to import private key");
    }
}

// Unwrap an AES key that was wrapped with RSA-OAEP
async function unwrapAesKey(wrappedKeyB64) {
    try {
        // Get the private RSA key
        const privateKey = await getPrivateKey();
        
        // Convert the base64 wrapped key to ArrayBuffer
        const wrappedKeyBuffer = b64ToArrayBuffer(wrappedKeyB64);
        
        // Unwrap the AES key
        return await window.crypto.subtle.unwrapKey(
            "raw", // the wrapped key format
            wrappedKeyBuffer, // the wrapped key data
            privateKey, // the unwrapping key
            {   // the unwrapping algorithm
                name: "RSA-OAEP",
                hash: {name: "SHA-256"}
            },
            {   // the unwrapped key algorithm
                name: "AES-GCM",
            },
            true, // extractable
            ["decrypt"] // what can be done with the unwrapped key
        );
    } catch (error) {
        console.error("Error unwrapping AES key:", error);
        
        // Fallback: Try importing as a raw key (for testing with non-wrapped keys)
        console.warn("Falling back to raw key import (test mode)");
        try {
            const rawKeyBuffer = b64ToArrayBuffer(wrappedKeyB64);
            return await window.crypto.subtle.importKey(
                "raw",
                rawKeyBuffer,
                { name: "AES-GCM" },
                false,
                ["decrypt"]
            );
        } catch (fallbackError) {
            console.error("Fallback key import also failed:", fallbackError);
            throw new Error("Failed to process encryption key");
        }
    }
}

// Decrypt data using AES-GCM
async function decryptData(encryptedData, key, iv) {
    try {
        // Decrypt the data
        const decryptedBuffer = await window.crypto.subtle.decrypt(
            {
                name: "AES-GCM",
                iv: iv,
                // Optional additional authenticated data
                tagLength: 128 // default for AES-GCM
            },
            key,
            encryptedData
        );
        
        return decryptedBuffer;
    } catch (error) {
        console.error("Decryption failed:", error);
        throw new Error(`AES-GCM decryption failed: ${error.message || error.name}`);
    }
}
