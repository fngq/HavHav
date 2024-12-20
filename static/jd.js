var http_get = function (url, params, callback) {
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

function add_task(callback) {
    let toadd = $("input#input_add_task").val();
    console.log(toadd);
    let url = "/api/task/add";
    $.getJSON(
        url = url,
        data = { "url": toadd },
        success = function (data) {
            console.log(data)
            update_task_list();
        }
    );
}


function task_list(callback) {
    var url = "/api/task/list"
    http_get(url, null, callback)
}

function update_task_list() {
    let cb = function (tasks) {
        let javlist = $("#javlist")
        javlist.empty()
        tasks.forEach(element => {
            javlist.append(createRow(element))
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
    http_get(url, null, callback)
}
function stop_task(name, callback) {
    var url = "/api/task/stop";
    http_get(url, { "name": name }, callback);
}
function start_task(name, callback) {
    var url = "/api/task/start";
    http_get(url, { "name": name }, callback);
}

function formatFileSize(bytes) {
    if (!bytes || bytes === 0) return '0 B';
    
    const units = ['B', 'KB', 'MB', 'GB', 'TB'];
    const k = 1024;
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + units[i];
}


function createRow(task) {
    // 创建图片
    const img = $('<img></img>')
    img.attr('src', task.cover)

    // 创建标题
    const title = $('<div>')
    title.attr('class', 'title')
    title.text(task.title || task.name)
    title.attr('title', task.title || task.name)  // 添加悬停提示

    // 创建进度条容器
    const progressContainer = $('<div>')
    progressContainer.attr('class', 'progress-container')
    strprogress = String(task.progress / task.total * 100)
    // 创建进度条
    const progress = $('<div>')
    progress.attr('class', 'progress')
    progress.css('width', strprogress + '%') // 设置进度条的宽度

    // 创建显示文字的元素
    const progressText = $('<div>')
    progressText.attr('class', 'progress-text')
    progressText.text(task.status) // 显示进度状态

    progress.append(progressText);

    // 将进度条放入进度条容器
    progressContainer.append(progress);

    const protxt = $('<div>')
    protxt.attr('class', 'progress-str')
    protxt.text(String(Math.floor(task.progress/task.total * 10000) / 100) + '%')
    if (task.status === 'Finished' && task.video_size){
        protxt.text(formatFileSize(task.video_size))
    }

    // 创建状态按钮
    const actionButton = $('<button>')
        .on('click', () => {
            if (task.status === 'Running') {
                // Stop 逻辑
                if (confirm(`确定要停止任务 "${task.name}" 吗？`)) {
                    stop_task(task.name, (response) => {
                        console.log('停止任务响应:', response);
                        update_task_list();
                    });
                }
            } else if (['Canceled', 'Failed'].includes(task.status)) {
                // Start 逻辑
                if (confirm(`确定要重新开始任务 "${task.name}" 吗？`)) {
                    start_task(task.name, (response) => {
                        console.log('重新开始任务:', task.name);
                        update_task_list();
                    });
                }
            }
        });

    // 根据任务状态设置按钮状态和文本
    if (task.status === 'Running') {
        actionButton.text('Stop')
            .attr('title', '点击停止任务');
    } else if (['Canceled', 'Failed'].includes(task.status)) {
        actionButton.text('Start')
            .attr('title', '点击重新开始任务');
    } else {
        actionButton.prop('disabled', true)
            .css('opacity', '0.5')
            .text('Stop')
            .attr('title', '任务无法操作');
    }

    // 创建 "下载" 链接
    const download = $('<a>')
        .attr('href', task.video_url)
        .text('下载')
        .attr('target', '_blank')
        .css({
            'white-space': 'nowrap',
            'flex-shrink': '0'  // 防止元素被压缩
        })
    // 只在有URL时添加href属性
    if (task.video_url) {
        download.attr('href', task.video_url)
    } else {
        download.css('pointer-events', 'none')  // 禁用点击
            .attr('title', '下载链接暂未生成')  // 添加提示文字
    }
    // 创建行 div
    const row = $('<div class="row"></div>')
    // 将所有元素添加到行中
    row.append(img);
    row.append(title);
    row.append(progressContainer);
    row.append(protxt)
    row.append(actionButton);
    row.append(download);

    // 将行元素添加到容器中
    return row;
};

jQuery(function () {
    $("button#btn_add_task").on("click", function () {
        add_task();
    });
    update_task_list();
    // 设置定时刷新
    const refreshInterval = 3000; // 5秒刷新一次
    let refreshTimer = setInterval(function () {
        update_task_list();
    }, refreshInterval);

    // 当页面隐藏时暂停刷新，显示时恢复
    document.addEventListener('visibilitychange', function () {
        if (document.hidden) {
            // 页面隐藏时清除定时器
            if (refreshTimer) {
                clearInterval(refreshTimer);
                refreshTimer = null;
            }
        } else {
            // 页面显示时重新启动定时器
            if (!refreshTimer) {
                update_task_list(); // 立即刷新一次
                refreshTimer = setInterval(function () {
                    update_task_list();
                }, refreshInterval);
            }
        }
    });

});