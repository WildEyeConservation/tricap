var $SCRIPT_ROOT = {{ request.script_root|tojson|safe }};

var numCams = {{num_cams}};

BUTTON_CODE_START = 0;
BUTTON_CODE_STOP = 1;

var buttonClickFollowUp = function () {
    console.log("Button Click Follow Up");
    return false;
}

var handleButtonClick = function(buttonCode){

    if (buttonCode === BUTTON_CODE_START ){
        $.getJSON($SCRIPT_ROOT + '/_button_click', {buttonCode: buttonCode }, buttonClickFollowUp)
    } else if (buttonCode === BUTTON_CODE_STOP){
        $.getJSON($SCRIPT_ROOT + '/_button_click', {buttonCode: buttonCode }, buttonClickFollowUp)
    }

    return false;

}

$(function () {
    var buttonClick = function (e) {
    console.log("Start Clicked");
    handleButtonClick(BUTTON_CODE_START);
    return false;
    };
    document.getElementById("btn_start").onclick = buttonClick
});

$(function () {
    var buttonClick = function (e) {
    console.log("Stop Clicked");
    handleButtonClick(BUTTON_CODE_STOP);
    return false;
    };
    document.getElementById("btn_stop").onclick = buttonClick
});


var camImageCheckFollowUp = function(data){
    if (data.new_image === true){
        var img = document.getElementById('img_cam'+data.cam_num)
        img.src = '/cam_img' + data.cam_num + '?'+ new Date().getTime();
    }
}

$(function () {
    var imgCheckupFunc = function(){
        for (index = 0; index < numCams; index++){
            console.log("Checking Cam Img" + index);
            $.getJSON($SCRIPT_ROOT + '/_check_cam_image'+index, {}, camImageCheckFollowUp)
        }
        return false;
    };
    setInterval(imgCheckupFunc, 5000);
});