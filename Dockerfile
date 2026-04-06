FROM python:3.14-slim 

WORKDIR /app

COPY requirements.txt ./

RUN pip install --no-cache-dir -r requirements.txt 
RUN pip install --no-cache-dir playwright 
# RUN playwright install --with-deps chromium

COPY . /app

# 暴露端口
EXPOSE 8090

# the resources will be saved to './downloads' directory after downloaded

CMD ["python", "main.py"]
