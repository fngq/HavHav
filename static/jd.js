var http_get = function(url, params, callback) {
    if (params) {
        const urlParams = new URLSearchParams(params).toString();
        url = url + "?" + urlParams
    }
    const xhr = new XMLHttpRequest();
    xhr.open('GET', url, true);
    xhr.onreadystatechange = function () {
        if (this.readyState == 4 && this.status == 200) {
            let d = JSON.parse(xhr.responseText)
            callback(d)
        }
    }
    xhr.send()

}

function add_task(callback){
    let toadd = $("input#input_add_task").val();
    console.log(toadd);
    let url = "/api/task/add";
    $.getJSON(
        url=url,
        data={"url":toadd},
        success = function(data){
            console.log(data)
            update_task_list();
        }
    );
}


function task_list(callback) {
    var url = "/api/task/list"
    http_get(url, null, callback)
}

function update_task_list(){
    let cb = function(tasks){
        let javlist = $("#javlist")
        javlist.empty()
        console.log(tasks)
        tasks.forEach(element => {
            createRow(element)
        });
    }
    task_list(cb);
}

function create_task(url, callback) {
    var url = "/api/task/add"
    http_get(url, null, callback)
}
function file_list(callback) {
    var url = "/api/file/list"
    http_get(url, nill, callback)
}
function stop_task(url, taskurl, callback) {
    var url = "/api/task/stop";
    http_get(url, { "url": taskurl }, callback);
}
function createRow(task) {
    // 获取容器
    const container = document.getElementById('javlist');
    // 创建行 div
    const row = document.createElement('div');
    row.className = 'row';

    // 创建图片
    const img = document.createElement('img');
    img.src = task.cover;

    // 创建标题
    const title = document.createElement('div');
    title.className = 'title';
    title.textContent = task.title;
    if (!task.title) {
        title.textContent = task.name
    }

    // 创建进度条容器
    const progressContainer = document.createElement('div');
    progressContainer.className = 'progress-container';
    strprogress = String(task.progress * 100)
    // 创建进度条
    const progress = document.createElement('div');
    progress.className = 'progress';
    progress.style.width = strprogress + '%'; // 设置进度条的宽度

    // 创建显示文字的元素
    const progressText = document.createElement('div');
    progressText.className = 'progress-text';
    progressText.textContent = task.state; // 显示进度状态

    progress.appendChild(progressText);

    // 将进度条放入进度条容器
    progressContainer.appendChild(progress);

    const protxt = document.createElement('div')
    protxt.className = 'progress-str'
    protxt.textContent = String(Math.floor(task.progress * 10000) / 100) + '%'

    // 创建 "stop" 按钮
    const stopButton = document.createElement('button');
    stopButton.textContent = 'Stop';
    stopButton.onclick = () => alert('Stopped');

    // 创建 "下载" 链接
    const download = document.createElement('a');
    download.href = task.file;
    download.textContent = '下载';
    download.target = '_blank'; // 在新标签页中打开链接

    // 将所有元素添加到行中
    row.appendChild(img);
    row.appendChild(title);
    row.appendChild(progressContainer);
    row.appendChild(protxt)
    row.appendChild(stopButton);
    row.appendChild(download);

    // 将行元素添加到容器中
    container.appendChild(row);
}

var tlist = document.getElementById('javlist');
task_list(function (tasks) {
    console.log(tasks)
    tasks.forEach(element => {
        createRow(element)
    });
});

jQuery(function(){
$("button#btn_add_task").on("click",function(){
    console.log("btn clicked");
    add_task();
});
console.log("document is ready")

});