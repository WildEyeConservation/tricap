// Code needed to give the camera template extra functionality
// All of the following code will only run when the page is ready
//  (the $() is short for $(document).ready())

var batteryWarning = 50; // Below 50 percent
var spaceWarning = 100000; // Below +-145Gb
//var battery0 = parseInt({{battery[0]}})

$(function(){
    // Check for low battery
    if({{battery[0]}} < batteryWarning || {{free_space[0]}} < spaceWarning){
        $('#middle_camera').removeClass('alert-info');
        $('#middle_camera').addClass('alert-danger');
    } else {
        $('#middle_camera').removeClass('alert-danger');
        $('#middle_camera').addClass('alert-info');
    }

    if({{battery[1]}} < batteryWarning || {{free_space[1]}} < spaceWarning){
        $('#front_camera').removeClass('alert-info');
        $('#front_camera').addClass('alert-danger');
    } else {
        $('#front_camera').removeClass('alert-danger');
        $('#front_camera').addClass('alert-info');
    }

    if({{battery[2]}} < batteryWarning || {{free_space[2]}} < spaceWarning){
        $('#back_camera').removeClass('alert-info');
        $('#back_camera').addClass('alert-danger');
    } else {
        $('#back_camera').removeClass('alert-danger');
        $('#back_camera').addClass('alert-info');
    }

//    $('#home_button').click(function{
//        $('#home_button').css("color", "yellow");
//    });
//
//    $("#home_button").hover(function(){
//        $(this).css("background-color", "yellow");
//        }, function(){
//        $(this).css("background-color", "orange");
//    });
});