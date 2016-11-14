LOG_CODE_ALL = 0

var populateLog = function(logCode){
    $.getJSON($SCRIPT_ROOT + '/_get_log', {logCode: logCode}, function(data){
        var pLog = document.getElementById('p_log');
        pLog.innerHTML = data.log;
    });
};

var Initialize = function() {
    populateLog(LOG_CODE_ALL);
    return false;
};

window.onload = Initialize;
