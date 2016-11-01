var $SCRIPT_ROOT = {{ request.script_root|tojson|safe }};

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

var camImage0CheckFollowUp = function(data){
    if (data.new_image === true){
        var img = document.getElementById('img_cam0')
        img.src = '/cam_img0?'+ new Date().getTime();
    }
}

$(function () {
    var checkCamImg0 = function(){
        console.log("Checking Cam Img 0");
        $.getJSON($SCRIPT_ROOT + '/_check_cam_image0', {}, camImage0CheckFollowUp)
        return false;
    }
    setInterval(checkCamImg0, 5000);
});