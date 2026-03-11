@echo off
echo ===================================================
echo Installing required python packages...
echo ===================================================
python -m pip install -r requirements.txt

echo.
echo ===================================================
echo Starting the Gilded Set-Master Streamlit App...
echo ===================================================
python -m streamlit run app.py

pause
