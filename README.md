# PerioVision AI: Dental Progression Prediction System

PerioVision AI is a production-level, AI-powered dental software designed for dentists to automatically analyze dental radiographs over time, measure periodontal bone loss, track disease progression, and predict future deterioration risks for each tooth.

## 🚀 Key Features

*   **Automated X-Ray Analysis**: Uses YOLOv8 (pose and segmentation) to detect teeth and extract key periodontal landmarks.
*   **Bone Loss Measurement**: Calculates percentage of bone loss based on alveolar bone levels and cemento-enamel junctions (CEJ).
*   **Longitudinal Tracking (TALPA)**: Measures progression velocity (%/year) by comparing current scans with historical patient data.
*   **Risk Prediction**: AI-driven risk assessment (Low, Medium, High) for future deterioration based on longitudinal trends and patient age.
*   **Interactive Disease Map**: Color-coded visual overlay showing severity levels (Healthy, Mild, Moderate, Severe) across all detected teeth.
*   **Practice Management**: Full-featured dashboard for managing patients, doctor appointments, and historical records using MongoDB.
*   **Secure Authentication**: Multi-factor authentication (2FA) for doctors and administrative role management.
*   **Clinical Reporting**: Instant generation of comprehensive PDF and CSV reports for patients.

## 🛠️ Technology Stack

*   **Frontend**: Streamlit (with custom Modern Glassmorphism UI).
*   **AI/CV**: Ultralytics YOLOv8, OpenCV, Scikit-learn.
*   **Database**: MongoDB.
*   **Reporting**: fpdf2, Plotly, Pandas.
*   **Security**: PyOTP for 2FA.

## 📦 Installation & Setup

1.  **Clone the Repository**:
    ```bash
    git clone <your-repository-url>
    cd Dental_progression
    ```

2.  **Install Dependencies**:
    ```bash
    pip install -r dental_progression_ai/requirements.txt
    ```

3.  **Environment Configuration**:
    Ensure MongoDB is running and update the connection URI if necessary in `dental_progression_ai/database/mongodb_connection.py`.

4.  **Run the Application**:
    ```bash
    cd dental_progression_ai
    streamlit run web_app/streamlit_app.py
    ```

## 📁 Repository Structure

*   `analysis/`: Logic for bone loss, progression, and risk assessment.
*   `database/`: MongoDB managers for patients, doctors, and records.
*   `image_processing/`: Pre-processing and alignment utilities.
*   `models/`: Pre-trained YOLOv8 weights and inference logic.
*   `report_generation/`: PDF/CSV export modules.
*   `web_app/`: Streamlit page modules and premium UI components.

---
*Developed for advanced clinical periodontal analysis.*
