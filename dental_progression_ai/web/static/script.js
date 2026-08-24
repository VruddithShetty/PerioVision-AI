// State Management
let currentDoctor = null;
let patientsList = [];
let csrfToken = '';

// DOM Elements
const authView = document.getElementById('auth-view');
const appView = document.getElementById('app-view');
const patientModal = document.getElementById('patient-modal');
const toast = document.getElementById('toast');
const toastMsg = document.getElementById('toast-msg');

// Initialization
document.addEventListener('DOMContentLoaded', async () => {
    await fetchCsrfToken();
    checkAuthStatus();
});

async function fetchCsrfToken() {
    try {
        const res = await fetch('/api/csrf-token');
        const data = await res.json();
        csrfToken = data.csrf_token;
    } catch (e) {
        console.error('Failed to fetch CSRF token');
    }
}

// ==========================================
// Toast Notifications
// ==========================================
function showToast(msg, isError = false) {
    toastMsg.textContent = msg;
    const icon = document.getElementById('toast-icon');
    
    if (isError) {
        toast.classList.remove('border-medical-500');
        toast.classList.add('border-red-500');
        icon.classList.remove('text-medical-500');
        icon.classList.add('text-red-500');
        icon.textContent = '⚠️';
    } else {
        toast.classList.add('border-medical-500');
        toast.classList.remove('border-red-500');
        icon.classList.add('text-medical-500');
        icon.classList.remove('text-red-500');
        icon.textContent = '✨';
    }

    toast.classList.remove('translate-x-full', 'opacity-0');
    
    setTimeout(() => {
        toast.classList.add('translate-x-full', 'opacity-0');
    }, 3000);
}

// ==========================================
// Authentication Logic
// ==========================================
async function checkAuthStatus() {
    try {
        const res = await fetch('/api/auth/status');
        const data = await res.json();
        if (data.logged_in) {
            currentDoctor = data.doctor;
            showAppView();
        } else {
            showAuthView();
        }
    } catch (e) {
        showAuthView();
    }
}

function showAuthView() {
    authView.classList.remove('hidden-view');
    appView.classList.add('hidden-view');
}

function showAppView() {
    authView.classList.add('hidden-view');
    appView.classList.remove('hidden-view');
    document.getElementById('user-profile-name').innerHTML = `Dr. ${currentDoctor.name}`;
    loadPatients();
}

function switchAuthTab(tab) {
    const btnLogin = document.getElementById('tab-login');
    const btnRegister = document.getElementById('tab-register');
    
    // Reset both
    btnLogin.className = "flex-1 pb-4 font-medium text-slate-400 border-b-2 border-transparent hover:text-slate-600 transition";
    btnRegister.className = "flex-1 pb-4 font-medium text-slate-400 border-b-2 border-transparent hover:text-slate-600 transition";
    
    document.getElementById('login-form').classList.add('hidden-view');
    document.getElementById('register-form').classList.add('hidden-view');

    // Set active
    document.getElementById(`tab-${tab}`).className = "flex-1 pb-4 font-semibold text-medical-600 border-b-2 border-medical-600 transition";
    document.getElementById(`${tab}-form`).classList.remove('hidden-view');
}

async function handleLogin(e) {
    e.preventDefault();
    const email = document.getElementById('login-email').value;
    const password = document.getElementById('login-password').value;

    const res = await fetch('/api/login', {
        method: 'POST',
        headers: { 
            'Content-Type': 'application/json',
            'X-CSRFToken': csrfToken
        },
        body: JSON.stringify({ email, password })
    });
    const data = await res.json();
    
    if (data.success) {
        showToast('Login successful!');
        checkAuthStatus();
    } else {
        showToast(data.error || 'Login failed', true);
    }
}

async function handleRegister(e) {
    e.preventDefault();
    const name = document.getElementById('reg-name').value;
    const email = document.getElementById('reg-email').value;
    const clinic_name = document.getElementById('reg-clinic').value;
    const password = document.getElementById('reg-password').value;

    const res = await fetch('/api/register', {
        method: 'POST',
        headers: { 
            'Content-Type': 'application/json',
            'X-CSRFToken': csrfToken
        },
        body: JSON.stringify({ name, email, clinic_name, password })
    });
    const data = await res.json();
    
    if (data.success) {
        showToast('Registration successful! Please login.');
        switchAuthTab('login');
        document.getElementById('login-email').value = email;
    } else {
        showToast(data.error || 'Registration failed', true);
    }
}

async function handleLogout() {
    await fetch('/api/logout', { 
        method: 'POST',
        headers: { 'X-CSRFToken': csrfToken }
    });
    currentDoctor = null;
    showAuthView();
}

// ==========================================
// Navigation
// ==========================================
function switchNav(section, element) {
    // Update active class
    document.querySelectorAll('.nav-btn').forEach(nav => {
        if(!nav.classList.contains('text-red-600')) {
            nav.className = "nav-btn text-slate-500 hover:text-slate-700 border-b-2 border-transparent font-medium px-1 py-5 transition";
        }
    });
    element.className = "nav-btn text-medical-600 border-b-2 border-medical-600 font-medium px-1 py-5 transition";

    // Hide all sections
    document.querySelectorAll('.page-section').forEach(sec => sec.classList.add('hidden-view'));
    
    // Show target section
    document.getElementById(`section-${section}`).classList.remove('hidden-view');
}

// ==========================================
// Patient Management
// ==========================================
function openAddPatientModal() {
    patientModal.classList.remove('hidden-view');
}

function closeAddPatientModal() {
    patientModal.classList.add('hidden-view');
    document.getElementById('add-patient-form').reset();
}

async function handleAddPatient(e) {
    e.preventDefault();
    const name = document.getElementById('pat-name').value;
    const age = document.getElementById('pat-age').value;
    const gender = document.getElementById('pat-gender').value;
    const contact = document.getElementById('pat-contact').value;
    const notes = document.getElementById('pat-notes').value;

    const res = await fetch('/api/patients', {
        method: 'POST',
        headers: { 
            'Content-Type': 'application/json',
            'X-CSRFToken': csrfToken
        },
        body: JSON.stringify({ name, age, gender, contact, notes })
    });
    const data = await res.json();
    
    if (data.success) {
        showToast('Patient added successfully!');
        closeAddPatientModal();
        loadPatients();
    } else {
        showToast(data.error || 'Failed to add patient', true);
    }
}

async function loadPatients() {
    const res = await fetch('/api/patients');
    const data = await res.json();
    
    if (data.success) {
        patientsList = data.patients;
        
        // Populate Dashboard Table
        const tbody = document.getElementById('patients-tbody');
        tbody.innerHTML = '';
        if (patientsList.length === 0) {
            tbody.innerHTML = '<tr><td colspan="4" class="px-6 py-12 text-center text-slate-500">No patients found. Add one to get started.</td></tr>';
        } else {
            patientsList.forEach(p => {
                const date = new Date(p.created_date).toLocaleDateString();
                tbody.innerHTML += `
                    <tr class="hover:bg-slate-50 transition">
                        <td class="px-6 py-4 whitespace-nowrap text-sm font-medium text-medical-600">#${p.patient_id}</td>
                        <td class="px-6 py-4 whitespace-nowrap text-sm text-slate-900 font-medium">${p.patient_name}</td>
                        <td class="px-6 py-4 whitespace-nowrap text-sm text-slate-500">${p.age} / ${p.gender}</td>
                        <td class="px-6 py-4 whitespace-nowrap text-sm text-slate-500">${date}</td>
                    </tr>
                `;
            });
        }

        // Populate Analyze Dropdown
        const select = document.getElementById('patient-select');
        select.innerHTML = '<option value="">-- Select Patient --</option>';
        patientsList.forEach(p => {
            select.innerHTML += `<option value="${p.patient_id}">${p.patient_name} (ID: ${p.patient_id})</option>`;
        });
    }
}

// ==========================================
// AI Pipeline Logic
// ==========================================
const dropZone = document.getElementById('drop-zone');
const fileInput = document.getElementById('file-input');
const previewImage = document.getElementById('preview-image');
const analyzeBtn = document.getElementById('analyze-btn');
const placeholder = document.querySelector('.upload-placeholder');
let currentFile = null;
let currentUploadId = null;
let currentRecordId = null;

// Drag & Drop
dropZone.addEventListener('click', () => fileInput.click());
dropZone.addEventListener('dragover', (e) => {
    e.preventDefault();
    dropZone.classList.add('border-medical-500', 'bg-medical-50');
});
dropZone.addEventListener('dragleave', () => {
    dropZone.classList.remove('border-medical-500', 'bg-medical-50');
});
dropZone.addEventListener('drop', (e) => {
    e.preventDefault();
    dropZone.classList.remove('border-medical-500', 'bg-medical-50');
    if (e.dataTransfer.files.length) {
        handleFileSelect(e.dataTransfer.files[0]);
    }
});
fileInput.addEventListener('change', (e) => {
    if (e.target.files.length) {
        handleFileSelect(e.target.files[0]);
    }
});

document.getElementById('patient-select').addEventListener('change', checkReadyState);

async function handleFileSelect(file) {
    currentFile = file;
    currentUploadId = null;
    
    if (!file.name.toLowerCase().endsWith('.dcm')) {
        const reader = new FileReader();
        reader.onload = (e) => {
            previewImage.src = e.target.result;
            previewImage.classList.remove('hidden-view');
            placeholder.classList.add('hidden-view');
            checkReadyState();
        };
        reader.readAsDataURL(file);
    } else {
        previewImage.classList.add('hidden-view');
        placeholder.innerHTML = `<p class="mt-4 text-sm text-medical-600 font-bold">DICOM File: ${file.name}</p>`;
        placeholder.classList.remove('hidden-view');
    }
    
    // Auto-upload to parse metadata
    const formData = new FormData();
    formData.append('image', file);
    try {
        const res = await fetch('/api/upload', {
            method: 'POST',
            headers: { 'X-CSRFToken': csrfToken },
            body: formData
        });
        const data = await res.json();
        if (data.success) {
            currentUploadId = data.upload_id;
            if (data.is_dcm && data.metadata) {
                const msg = `DICOM Metadata Found:\nPatient: ${data.metadata.PatientName || 'Unknown'} (ID: ${data.metadata.PatientID || 'Unknown'})\nDate: ${data.metadata.StudyDate || 'Unknown'}\n\nPlease ensure you have selected or created the corresponding Patient Record below before analyzing.`;
                alert(msg);
            }
        } else {
            showToast('Failed to process upload: ' + data.error, true);
        }
    } catch (e) {
        showToast('Upload error', true);
    }
    
    checkReadyState();
}

function checkReadyState() {
    const patientId = document.getElementById('patient-select').value;
    if (patientId && currentFile) {
        analyzeBtn.disabled = false;
    } else {
        analyzeBtn.disabled = true;
    }
}

analyzeBtn.addEventListener('click', async () => {
    const patientId = document.getElementById('patient-select').value;
    
    // UI State update
    analyzeBtn.disabled = true;
    document.getElementById('results-content').classList.add('hidden-view');
    document.querySelector('.empty-state').classList.add('hidden-view');
    document.getElementById('loading-state').classList.remove('hidden-view');

    const formData = new FormData();
    if (currentUploadId) {
        formData.append('upload_id', currentUploadId);
    } else {
        formData.append('image', currentFile);
    }
    formData.append('patient_id', patientId);

    try {
        const response = await fetch('/api/analyze', {
            method: 'POST',
            headers: {
                'X-CSRFToken': csrfToken
            },
            body: formData
        });
        
        const result = await response.json();
        
        document.getElementById('loading-state').classList.add('hidden-view');
        
        if (result.success) {
            currentRecordId = result.record_id;
            document.getElementById('results-content').classList.remove('hidden-view');
            
            // Generate cache-busting URL for the image
            const imgUrl = `/api/image?path=${encodeURIComponent(result.annotated_path)}&t=${new Date().getTime()}`;
            document.getElementById('annotated-result-img').src = imgUrl;

            const tbody = document.getElementById('metrics-tbody');
            tbody.innerHTML = '';
            
            result.analysis.teeth.forEach(t => {
                let riskClass = t.risk_level === 'High' ? 'text-red-600 bg-red-50' : 
                               (t.risk_level === 'Medium' ? 'text-amber-600 bg-amber-50' : 'text-emerald-600 bg-emerald-50');
                               
                let gradeClass = t.talpa_grade === 'Grade C' ? 'text-red-600 bg-red-50 border border-red-200' :
                                (t.talpa_grade === 'Grade B' ? 'text-amber-600 bg-amber-50 border border-amber-200' : 'text-emerald-600 bg-emerald-50 border border-emerald-200');
                               
                tbody.innerHTML += `
                    <tr>
                        <td class="px-4 py-3 whitespace-nowrap text-sm font-semibold text-slate-900">${t.tooth_id}</td>
                        <td class="px-4 py-3 whitespace-nowrap text-sm text-slate-700">${t.bone_loss_pct.toFixed(1)}%</td>
                        <td class="px-4 py-3 whitespace-nowrap text-sm text-slate-700">${t.severity}</td>
                        <td class="px-4 py-3 whitespace-nowrap text-sm font-mono text-slate-600">${t.velocity_per_year.toFixed(2)}</td>
                        <td class="px-4 py-3 whitespace-nowrap text-sm"><span class="px-2 py-1 rounded shadow-sm font-bold text-xs ${gradeClass}">${t.talpa_grade}</span></td>
                        <td class="px-4 py-3 whitespace-nowrap text-sm"><span class="px-2 py-1 rounded-md font-medium text-xs ${riskClass}">${t.risk_level}</span></td>
                    </tr>
                `;
            });
            showToast('Diagnostic Pipeline complete!');
        } else {
            document.querySelector('.empty-state').classList.remove('hidden-view');
            showToast('Analysis failed: ' + result.error, true);
        }
    } catch (err) {
        document.getElementById('loading-state').classList.add('hidden-view');
        document.querySelector('.empty-state').classList.remove('hidden-view');
        showToast('Connection error occurred', true);
    }
    
    analyzeBtn.disabled = false;
});

document.getElementById('download-report-btn').addEventListener('click', () => {
    if (currentRecordId) {
        window.location.href = `/api/report/${currentRecordId}`;
    }
});
